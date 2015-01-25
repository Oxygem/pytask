# pytask
# File: pytask.py
# Desc: provides a framework for managing & running greenlet based tasks

import time
import json
import logging
from uuid import uuid4

import gevent


def run_loop(function, interval):
    '''Like setInterval, slight time drift as usual, useful in tasks as well as here'''
    while True:
        before = time.time()
        function()

        duration = time.time() - before
        if duration < interval:
            gevent.sleep(interval - duration)


class Task(object):
    '''An individual task base'''
    # Internal task_id
    _id = None
    # Internal task state
    _state = 'WAIT'
    # Redis object
    _redis = None
    # & channel name
    _channel = None
    # Clean me up?
    _cleanup = None

    def __init__(self, **task_data):
        self.task_data = task_data

    def emit(self, event, data=None):
        '''Emit task events -> pubsub channel'''
        self._redis.publish(self._channel, json.dumps({
            'event': event,
            'data': data
        }))

    # Tasks which don't define a stop are assumed not to spawn any sub-greenlets
    # this is called before we kill the task's greenlet (running task.start)
    def stop(self):
        pass


class PyTask(object):
    '''
    A daemon that starts/stops tasks & replicates that to a Redis instance
    tasks can be control via Redis pubsub
    '''
    TASKS = {}

    # Active tasks
    tasks = {}
    # Task greenlets (id -> greenlet)
    greenlets = {}
    # Tasks to start on run
    pre_start_tasks = []
    pre_start_task_ids = []
    # Pubsub
    pattern_subscriptions = {}
    channel_subscriptions = {}
    # Custom exception handlers
    exception_handlers = []

    ### Default config
    # new_task_interval = when to check for new tasks (s)
    def __init__(self, redis_instance,
        task_set='tasks', task_prefix='task-',
        new_queue='new-task', end_queue='end-task',
        new_task_interval=1, update_task_interval=5, cleanup_tasks=False
    ):
        self.new_task_interval = new_task_interval
        self.update_task_interval = update_task_interval
        self.cleanup_tasks = cleanup_tasks
        self.logger = logging.getLogger('pytask')

        # Set Redis instance & config constants
        self.redis = redis_instance
        self.REDIS_TASK_SET = task_set
        self.REDIS_TASK_PREFIX = task_prefix
        self.REDIS_NEW_QUEUE = new_queue
        self.REDIS_END_QUEUE = end_queue

        # Setup Redis pubsub
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(None) # has to be called before we can get_message


    ### Public api
    def run(self, task_map=None):
        '''Run pytask, basically a wrapper to handle tick count & KeyboardInterrupt'''
        if task_map:
            self.TASKS.update(task_map)

        self.logger.debug('Starting up...')
        self.logger.debug('Loaded tasks: {0}'.format(self.TASKS.keys()))

        # Start the get new tasks loop
        new_task_loop = gevent.spawn(run_loop, self._get_new_tasks, self.new_task_interval)
        # Start the update task loop
        task_update_loop = gevent.spawn(run_loop, self._update_tasks, self.update_task_interval)
        # Start reading from Redis pubsub
        pubsub_loop = gevent.spawn(self._pubsub)

        for (task_name, task_data) in self.pre_start_tasks:
            self._pre_start_task(task_name, task_data)

        try:
            # If this ever returns, something broke...
            gevent.wait([new_task_loop, pubsub_loop, task_update_loop])
        except KeyboardInterrupt:
            # ... or the user/process asked us to quit!
            self.logger.info('Exiting upon user command...')
            # Stop our loops
            new_task_loop.kill()
            pubsub_loop.kill()
            task_update_loop.kill()
            # Stop & requeue all running tasks (for another worker/etc)
            for task_id in self.tasks.keys():
                if task_id in self.pre_start_task_ids:
                    continue

                # Set state STOPPED
                self._stop_task(task_id)
                # Remove from the active task list
                self.redis.srem(self.REDIS_TASK_SET, task_id)
                # Requeue for another worker
                self.redis.lpush(self.REDIS_NEW_QUEUE, task_id)

    def pre_start_task(self, task_name, task_data=None):
        '''Used to start tasks on this worker (no queue), before calling .run'''
        if task_data is None:
            task_data = {}

        self.pre_start_tasks.append((task_name, task_data))

    def add_task(self, task_class):
        '''Add a task class'''
        self.TASKS[task_class.NAME] = task_class

    def add_exception_handler(self, handler):
        '''Add an exception handler'''
        self.exception_handlers.append(handler)


    ### Internal task management
    def _task_name(self, task_id):
        return '{0}{1}'.format(
            self.REDIS_TASK_PREFIX,
            task_id
        )

    def _pre_start_task(self, task_name, task_data):
        '''Starts a task on *this* worker'''
        # Generate task_id
        task_id = str(uuid4())
        self.pre_start_task_ids.append(task_id)

        # Write task hash to Redis
        self.redis.hmset(self._task_name(task_id), {
            'task': task_name,
            'data': json.dumps(task_data)
        })

        # Add the task
        self._add_task(task_id)

    def _add_task(self, task_id):
        '''Interally add a task from the new-task queue'''
        self.logger.debug('New task: {0}'.format(task_id))

        # Read the task hash
        task_class, task_data, cleanup = self.redis.hmget(self._task_name(task_id), ['task', 'data', 'cleanup'])

        # No cleanup = PyTask default
        cleanup = self.cleanup_tasks if cleanup is None else cleanup == 'true'
        if task_data is None:
            task_data = {}

        if task_class not in self.TASKS:
            self.logger.critical('Task not found: {}'.format(task_class))
            return

        # Create task instance, assign it Redis
        try:
            task = self.TASKS[task_class](**json.loads(task_data))
        except Exception as e:
            self.logger.critical('Task {0} failed to initialize with exception: {1}'.format(
                task_class, e
            ))
            # Set Redis data
            self.redis.hmset(self._task_name(task_id), {
                'state': 'EXCEPTION',
                'exception_data': str(e)
            })

            # Run exception handlers
            for handler in self.exception_handlers:
                handler(e)

            return

        task._id = task_id
        task._redis = self.redis
        task._channel = self._task_name(task_id)
        task._cleanup = cleanup

        # Add to Redis set
        self.redis.sadd(self.REDIS_TASK_SET, task_id)

        # Set Redis data
        self.redis.hmset(self._task_name(task_id), {
            'state': 'RUNNING',
            'last_update': time.time()
        })

        # Subscribe to control channel
        self._subscribe(
            lambda message: self._control_task(task_id, message),
            channel='{}-control'.format(self._task_name(task_id))
        )

        # Assign the task internally & pass to _start_task
        self.tasks[task_id] = task
        self._start_task(task_id)
        self.logger.info('Task {0} added with ID {1}'.format(task_class, task_id))

    def _control_task(self, task_id, message):
        '''Handle control pubsub messages'''
        if message == 'stop':
            self._stop_task(task_id)
        elif message == 'start':
            self._start_task(task_id)
        elif message =='reload':
            self._reload_task(task_id)
        else:
            self.logger.warning('Unknown control command: {0}'.format(message))

    def _stop_task(self, task_id):
        '''Stops a task and kills/removes the greenlet'''
        if self.tasks[task_id]._state == 'STOPPED': return
        self.logger.debug('Stopping task: {0}'.format(task_id))

        # Stop the task
        self.tasks[task_id].stop()
        # End/delete it's greenlet
        self.greenlets[task_id].kill()

        # Set STOPPED in task & Redis
        self.tasks[task_id]._state = 'STOPPED'
        self.redis.hset(self._task_name(task_id), 'state', 'STOPPED')

    def _start_task(self, task_id):
        '''Starts a task in a new greenlet'''
        if self.tasks[task_id]._state == 'RUNNING': return
        self.logger.debug('Starting task: {0}'.format(task_id))

        greenlet = gevent.spawn(self.tasks[task_id].start)
        greenlet.link(lambda glet: self._on_task_end(task_id, glet))
        greenlet.link_exception(lambda glet: self._on_task_exception(task_id, glet))
        self.greenlets[task_id] = greenlet

        # Set running state
        self.tasks[task_id]._state = 'RUNNING'
        self.redis.hset(self._task_name(task_id), 'state', 'RUNNING')

    def _reload_task(self, task_id):
        '''Reload a tasks data by stopping/re-init-ing/starting'''
        self.logger.debug('Reloading task: {0}'.format(task_id))
        self._stop_task(task_id)

        # Reload task data from Redis
        task_data = self.redis.hget(self._task_name(task_id), 'data')

        # Re-init & start the task
        self.tasks[task_id].__init__(**json.loads(task_data))
        self._start_task(task_id)

    def _on_task_exception(self, task_id, greenlet):
        '''Handle exceptions in running tasks'''
        self.logger.warning('Exception in task: {0}: {1}'.format(task_id, greenlet.exception))

        # Set error state
        self.tasks[task_id]._state = 'EXCEPTION'
        self.redis.hmset(self._task_name(task_id), {
            'state': 'EXCEPTION',
            'exception_data': str(greenlet.exception)
        })

        # Emit the exception event
        self.tasks[task_id].emit('exception', str(greenlet.exception))

        # Run exception handlers
        for handler in self.exception_handlers:
            handler(greenlet.exception)

    def _on_task_end(self, task_id, greenlet):
        '''Handle tasks which have ended properly, either with success or failure'''
        if self.tasks[task_id]._state == 'STOPPED':
            return

        return_values = greenlet.get(block=False)
        if isinstance(return_values, tuple):
            status, data = return_values
        else:
            status, data = return_values, None

        # Set task's end data
        if data is not None:
            self.redis.hset(self._task_name(task_id), 'end_data', json.dumps(data))

        state = 'ERROR' if status is False else 'COMPLETE'
        # Set the tasks state
        self.redis.hset(self._task_name(task_id), 'state', state)
        # Emit complete/error
        self.tasks[task_id].emit(state.lower(), data)

        # Cleanup
        self._cleanup_task(task_id)
        self.logger.info('Task ended: {0}, state = {1}, data = {2}'.format(task_id, state, data))

    def _cleanup_task(self, task_id):
        '''Cleanup tasks in Redis and/or PyTask instance, depending on _cleanup setting'''
        if self.tasks[task_id]._cleanup:
            # Delete the hash
            self.redis.delete(self._task_name(task_id))

            # Remove the ID from the set
            self.redis.srem(self.REDIS_TASK_SET, task_id)

        # No cleanup, just push to the end-queue for cleanup
        else:
            self.redis.lpush(self.REDIS_END_QUEUE, task_id)

        # Remove internal task
        del self.tasks[task_id]
        del self.greenlets[task_id]

    def _get_new_tasks(self):
        '''Check for new tasks in Redis'''
        new_task_id = self.redis.rpop(self.REDIS_NEW_QUEUE)
        if new_task_id is not None:
            self._add_task(new_task_id)
            self._get_new_tasks()

    def _update_tasks(self):
        '''Update RUNNING task times in Redis, handle ended tasks'''
        update_time = time.time()

        for task_id, task in self.tasks.iteritems():
            if task._state != 'RUNNING': continue

            # Task still chugging along, update it's time
            self.redis.hset(self._task_name(task_id), 'last_update', update_time)


    ### Redis pubsub helpers
    def _pubsub(self):
        '''Check for Redis pubsub messages, apply to matching pattern/channel subscriptions'''
        while True:
            message = self.pubsub.get_message()
            if message and message['type'] == 'message':
                if message['pattern'] in self.pattern_subscriptions:
                    for callback in self.pattern_subscriptions[message['pattern']]:
                        callback(message['data'])

                if message['channel'] in self.channel_subscriptions:
                    for callback in self.channel_subscriptions[message['channel']]:
                        callback(message['data'])

                # Check for another message
                self._pubsub()
            gevent.sleep(.5)

    def _subscribe(self, callback, channel=None, pattern=None):
        '''Subscribe to Redis pubsub messages'''
        if channel is not None:
            self.channel_subscriptions.setdefault(channel, []).append(callback)
            self.pubsub.subscribe(channel)

        if pattern is not None:
            self.pattern_subscriptions.setdefault(pattern, []).append(callback)
            self.pubsub.psubscribe(pattern)
