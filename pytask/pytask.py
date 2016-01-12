# pytask
# File: pytask/pytask.py
# Desc: provides a framework for managing & running greenlet based tasks

import json
import logging
from time import time
from uuid import uuid4

import gevent

from .task import Task
from .helpers import run_loop, PyTaskHelpers, PyTaskRedisConf


class PyTask(PyTaskRedisConf):
    '''
    A daemon that starts/stops tasks & replicates that to a Redis instance
    tasks can be control via Redis pubsub.

    Redis Instance:
        The first argument can be either a Redis client or a list of host/port details.
        When using a list, pytask will use ``redis-py`` with one host and
        ``redis-py-cluster`` where multiple hosts are present.

    Args:
        redis_instance (client or list): Redis client or list of ``(host, port)`` tuples
        task_set (str): name of task set
        task_prefix (str): prefix for task names
        new_queue (str): queue to read new task IDs from
        end_queue (str): where to push complete task IDs
        new_task_interval (int): interval in s to check for new tasks
        update_task_interval (int): interval in s to update task times
    '''

    _task_classes = {}

    # Active tasks
    _tasks = {}

    # Task greenlets (id -> greenlet)
    _task_greenlets = {}

    # Local tasks
    _local_tasks = []
    _local_task_ids = []

    # Pubsub
    _channel_subscriptions = {}

    # Custom exception handlers
    _exception_handlers = []

    logger = logging.getLogger('pytask')

    def __init__(self, redis_instance,
        new_task_interval=1, update_task_interval=5,
        **kwargs
    ):
        # Set Redis config
        super(PyTask, self).__init__(redis_instance, **kwargs)

        self.new_task_interval = new_task_interval
        self.update_task_interval = update_task_interval

        # Setup Redis pubsub
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(None) # has to be called before we can get_message

        # Create helpers instance with related Redis config
        self.helpers = PyTaskHelpers(redis_instance, **kwargs)

    # Public api
    #

    def run(self, task_map=None):
        '''Run pytask, basically a wrapper to handle KeyboardInterrupt.'''

        if task_map:
            self._task_classes.update(task_map)

        self.logger.debug('Starting up...')
        self.logger.debug('Loaded tasks: {0}'.format(self._task_classes.keys()))

        # Start the get new tasks loop
        new_task_loop = gevent.spawn(
            run_loop, self._get_new_tasks, self.new_task_interval
        )

        # Start the update task loop
        task_update_loop = gevent.spawn(
            run_loop, self._update_tasks, self.update_task_interval
        )

        # Start reading from Redis pubsub
        pubsub_loop = gevent.spawn(self._pubsub)

        # Kick off any _local_tasks
        for (task_name, task_data) in self._local_tasks:
            self._start_local_task(task_name, task_data)

        # If this ever exits, something broke...
        try:
            gevent.wait([new_task_loop, pubsub_loop, task_update_loop])

        # Handle normal SIGINT exit - requeue anything running
        except KeyboardInterrupt:
            self.logger.info('Exiting upon user command...')

            # Stop & requeue all running tasks (for another worker/etc)
            for task_id in self._tasks.keys():
                # Stop the task
                self._stop_task(task_id)

                # If this wasn't a local task, requeue it
                if task_id not in self._local_task_ids:
                    self.logger.info('Requeuing task: {0}'.format(task_id))
                    self.redis.lpush(self.NEW_QUEUE, task_id)

        # Always cleanup the workers, whether SIGINT or some other crash
        finally:
            new_task_loop.kill()
            pubsub_loop.kill()
            task_update_loop.kill()

    def start_local_task(self, task_name, task_data=None):
        '''
        Used to start local tasks on this worker, which will start when ``.run`` is
        called.
        '''

        if task_data is None:
            task_data = {}

        self._local_tasks.append((task_name, task_data))

    def add_task(self, task_class):
        '''Add a task class.'''

        self._task_classes[task_class.NAME] = task_class

    def add_tasks(self, *task_classes):
        '''Add multiple task classes.'''

        for task_class in task_classes:
            self.add_task(task_class)

    def add_exception_handler(self, handler):
        '''Add an exception handler.'''

        self._exception_handlers.append(handler)

    # Internal API
    #

    def _start_local_task(self, task_name, task_data):
        '''Starts a task on *this* worker.'''

        # Generate task_id
        task_id = str(uuid4())
        self._local_task_ids.append(task_id)

        # Write task hash to Redis
        self.helpers.set_task(task_id, {
            'task': task_name,
            'data': json.dumps(task_data),
            'local': 'true'
        })

        # Add the task
        self._add_task(task_id)

    def _add_task(self, task_id):
        '''Interally add a task from the new-task queue.'''

        self.logger.debug('New task: {0}'.format(task_id))

        # Read the task hash
        task_hash = self.helpers.get_task(task_id, ['task', 'data'])
        if not task_hash:
            self.logger.critical('Task ID in queue but no hash: {0}'.format(task_id))
            return

        if task_hash:
            task_class, task_data = task_hash

        if task_data is None:
            task_data = {}

        if task_class not in self._task_classes:
            self.logger.critical('Task not found: {0}'.format(task_class))
            return

        # Create task instance, assign it Redis
        try:
            task = self._task_classes[task_class](**json.loads(task_data))

        except Exception as e:
            self.logger.critical(
                'Task {0} failed to initialize with exception: {1}'.format(task_class, e)
            )

            # Set Redis data
            self.helpers.set_task(task_id, {
                'state': 'EXCEPTION',
                'output': str(e)
            })

            # Run exception handlers
            for handler in self._exception_handlers:
                handler(e)

            return

        task._id = task_id
        task._redis = self.redis
        # Publishing channel is the task id
        task._channel = self.task_key(task_id)

        # Add to Redis set
        self.redis.sadd(self.TASK_SET, task_id)

        # Set Redis data
        self.helpers.set_task(task_id, {
            'state': 'RUNNING',
            'last_update': time()
        })

        # Subscribe to control channel
        self._subscribe(
            self.task_control(task_id),
            lambda message: self._control_task(task_id, message)
        )

        # Assign the task internally & pass to _start_task
        self._tasks[task_id] = task
        self._start_task(task_id)
        self.logger.info('Task {0} added with ID {1}'.format(task_class, task_id))

    def _control_task(self, task_id, message):
        '''Handle control pubsub messages.'''

        if message == 'stop':
            self._stop_task(task_id)

        elif message == 'reload':
            self._reload_task(task_id)

        else:
            self.logger.warning('Unknown control command: {0}'.format(message))

    def _start_task(self, task_id):
        '''Starts a task in a new greenlet.'''

        self.logger.debug('Starting task: {0}'.format(task_id))
        task = self._tasks[task_id]

        greenlet = gevent.spawn(task.start)

        # Handle task complete
        greenlet.link(lambda glet: self._on_task_success(task_id, glet))
        # And task error & exceptions
        greenlet.link_exception(lambda glet: self._on_task_exception(task_id, glet))

        self._task_greenlets[task_id] = greenlet

        # Set internal & Redis state
        task._state = 'RUNNING'
        self.helpers.set_task(task_id, 'state', 'RUNNING')

    def _reload_task(self, task_id):
        '''Reload a tasks data by stopping/re-init-ing/starting.'''

        self.logger.debug('Reloading task: {0}'.format(task_id))
        task = self._tasks[task_id]

        # Stop the task
        task.stop()

        # End it's greenlet
        self._task_greenlets[task_id].kill()

        # Reload task data from Redis
        task_data = self.helpers.get_task(task_id, 'data')

        # Re-init & start the task
        task.__init__(**json.loads(task_data))
        self._start_task(task_id)

    def _stop_task(self, task_id):
        '''Stops a task and kills/removes the greenlet.'''

        self.logger.debug('Stopping task: {0}'.format(task_id))
        task = self._tasks[task_id]

        # Stop the task
        task.stop()

        # End it's greenlet
        self._task_greenlets[task_id].kill()

        # Set STOPPED in task & Redis
        task._state = 'STOPPED'
        self.helpers.set_task(task_id, 'state', 'STOPPED')

        # Cleanup internal Task, but don't push to the end queue
        self._cleanup_task(task_id, enqueue=False)

    def _handle_end_task(self, task_id, state, output, log_func=None):
        '''Shortcut for repeated steps in handling task exceptions/errors/successes.'''

        if log_func:
            log_func('{0} in task: {1}: {2}'.format(
                state.lower().title(), task_id, output)
            )

        task = self._tasks[task_id]

        # Set internal & Redis state
        task._state = state
        self.helpers.set_task(task_id, {
            'state': state,
            'output': output
        })

        # Emit the event
        task.emit(state.lower(), output)

    def _on_task_exception(self, task_id, greenlet):
        '''Handle exceptions in running tasks.'''

        # If this is an Error exception, ie raised by the task, handle as such
        if isinstance(greenlet.exception, Task.Error):
            return self._on_task_error(task_id, greenlet)

        data = unicode(greenlet.exception)

        self._handle_end_task(
            task_id, 'EXCEPTION', data,
            log_func=self.logger.warning
        )

        # Run exception handlers
        for handler in self._exception_handlers:
            handler(greenlet.exception)

        # Cleanup
        self._cleanup_task(task_id)

    def _on_task_error(self, task_id, greenlet):
        '''Handle tasks which have raised a ``Task.Error``.'''

        data = greenlet.exception.message

        self._handle_end_task(
            task_id, 'error', data,
            log_func=self.logger.info
        )

        self._cleanup_task(task_id)

    def _on_task_success(self, task_id, greenlet):
        '''Handle tasks which have ended successfully.'''

        data = greenlet.get(block=False)

        self._handle_end_task(
            task_id, 'SUCCESS', data,
            log_func=self.logger.info
        )

        self._cleanup_task(task_id)

    def _cleanup_task(self, task_id, enqueue=True):
        '''
        Internal PyTask cleanup and push from worker -> end queue.
        '''

        # Unsubscribe from control messages
        self._unsubscribe(self.task_control(task_id))

        # Remove internal task
        del self._tasks[task_id]
        del self._task_greenlets[task_id]

        if enqueue:
            # Delete the task_id from the "active" set
            self.redis.srem(self.TASK_SET, task_id)

            # Push to the end queue
            self.redis.lpush(self.END_QUEUE, task_id)

    def _get_new_tasks(self):
        '''Check for new tasks in Redis.'''

        new_task_id = self.redis.rpop(self.NEW_QUEUE)

        if new_task_id is not None:
            self._add_task(new_task_id)
            self._get_new_tasks()

    def _update_tasks(self):
        '''Update RUNNING task times in Redis.'''

        update_time = time()

        for task_id, task in self._tasks.iteritems():
            if task._state != 'RUNNING':
                continue

            # Task still chugging along, update it's time
            self.helpers.set_task(task_id, 'last_update', update_time)

    # Redis pubsub
    #

    def _get_pubsub_message(self):
        message = self.pubsub.get_message()

        if (
            message and message['type'] == 'message'
            and message['channel'] in self._channel_subscriptions
        ):
            self._channel_subscriptions[message['channel']](message['data'])

        return message

    def _pubsub(self):
        '''
        Check for Redis pubsub messages, apply to matching pattern/channel subscriptions.
        '''

        while True:
            # Read messages until we have no more
            while self._get_pubsub_message() is not None:
                pass

            gevent.sleep(.5)

    def _subscribe(self, channel, callback):
        '''Subscribe to Redis pubsub messages.'''

        self._channel_subscriptions[channel] = callback
        self.pubsub.subscribe(channel)

    def _unsubscribe(self, channel):
        '''Unsubscribe from Redis pubsub messages.'''

        if channel in self._channel_subscriptions:
            self.pubsub.unsubscribe(channel)
            del self._channel_subscriptions[channel]
