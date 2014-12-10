# pytask
# File: pytask.py
# Desc: provides a framework for managing & running greenlet based tasks

import time
import json
import logging
from uuid import uuid4

import gevent


# Like setInterval, slight time drift as usual
# useful in tasks as well as here
def run_loop(function, interval):
    while True:
        before = time.time()
        function()

        duration = time.time() - before
        if duration < interval:
            gevent.sleep(interval - duration)


class Task(object):
    # Internal task_id
    _id = None
    # Internal task state
    _state = 'WAIT'
    # PyTask pubsub object
    _pubsub = None
    # & channel name
    _channel = None

    # Emit task events -> pubsub channel
    def emit(self, event, data):
        self._pubsub.publish(self._channel, json.dumps({
            'event': event,
            'data': data
        }))

    # Tasks which don't define a stop are assumed not to spawn any sub-greenlets
    def stop(self):
        pass


class PyTask(object):
    REDIS = None
    TASKS = {}

    # Active tasks
    tasks = {}
    # Task greenlets (id -> greenlet)
    greenlets = {}
    # Tasks to start on run
    pre_start_tasks = []
    # Pubsub
    pattern_subscriptions = {}
    channel_subscriptions = {}

    ### Default config
    # new_task_interval = when to check for new tasks (s)
    def __init__(self, redis_instance,
        task_set='tasks', new_queue='new-task', end_queue='end-task', task_prefix='task-',
        new_task_interval=1, update_task_interval=5, task_stop_timeout=300
    ):
        self.new_task_interval = new_task_interval
        self.update_task_interval = update_task_interval
        self.task_stop_timeout = task_stop_timeout
        self.logger = logging.getLogger('pytask')

        # Set Redis instance & config constants
        self.redis = redis_instance
        self.REDIS = {
            'TASK_SET': task_set,
            'NEW_QUEUE': new_queue,
            'END_QUEUE': end_queue,
            'TASK_PREFIX': task_prefix
        }

        # Setup Redis pubsub
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(None) # has to be called before we can get_message


    ### Public api
    # Run pytask, basically a wrapper to handle tick count & KeyboardInterrupt
    def run(self, task_map=None):
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

    # Used to start tasks on this worker (no queue), before calling .run
    def pre_start_task(self, task_name, task_data=None):
        if task_data is None:
            task_data = {}

        self.pre_start_tasks.append((task_name, task_data))

    # Add a task class
    def add_task(self, task_class):
        self.TASKS[task_class.NAME] = task_class


    ### Internal task management
    # Starts a task on *this* worker
    def _pre_start_task(self, task_name, task_data):
        # Generate task_id
        task_id = str(uuid4())

        # Write task hash to Redis
        self.redis.hmset('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id,
        ), {
            'function': task_name,
            'data': json.dumps(task_data)
        })

        # Add the task
        self._add_task(task_id)

    # Interally add a task from the new-task queue
    def _add_task(self, task_id):
        self.logger.debug('New task: {0}'.format(task_id))

        # Check if task exists, exit if so (assume duplicate queue push)
        task_exists = self.redis.sismember(self.REDIS['TASK_SET'], task_id)
        if task_exists: return

        # Read the task hash
        task_class, task_data = self.redis.hmget('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id
        ), ['function', 'data'])

        if task_data is None:
            task_data = {}

        # Create task instance, assign it Redis
        try:
            task = self.TASKS[task_class](**json.loads(task_data))
        except Exception as e:
            self.logger.critical('Task {0} failed to initialize with exception: {1}'.format(
                task_class, e
            ))
            return

        task._id = task_id
        task._pubsub = self.pubsub
        task._channel = '{0}{1}'.format(self.REDIS['TASK_PREFIX'], task_id)

        # Add to Redis set
        self.redis.sadd(self.REDIS['TASK_SET'], task_id)

        # Set Redis data
        self.redis.hmset('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id,
        ), {
            'state': 'RUNNING',
            'last_update': time.time()
        })

        # Handle control messages
        def on_control(message):
            if message == 'stop':
                self._stop_task(task_id)
            elif message == 'start':
                self._start_task(task_id)
            elif message =='reload':
                self._reload_task(task_id)
            else:
                self.logger.warning('Unknown control command: {0}'.format(message))

        # Subscribe to control channel
        self._subscribe(on_control, channel='{0}{1}-control'.format(
            self.REDIS['TASK_PREFIX'],
            task_id
        ))

        # Assign the task internally & pass to _start_task
        self.tasks[task_id] = task
        self._start_task(task_id)
        self.logger.info('Task {0} added with ID {1}'.format(task_class, task_id))

    # Stop a task & remove it's greenlet
    def _stop_task(self, task_id):
        # TODO: better check for already-stopped task

        self.logger.debug('Stopping task: {0}'.format(task_id))

        self.tasks[task_id].stop()
        self.greenlets[task_id].kill()

        # Set STOPPED in task & Redis
        self.tasks[task_id]._state = 'STOPPED'

    # Start a task in a new greenlet
    def _start_task(self, task_id):
        # TODO: better checks for already-running task

        self.logger.debug('Starting task: {0}'.format(task_id))
        self.greenlets[task_id] = gevent.spawn(self.tasks[task_id].start)
        self.greenlets[task_id].link_exception(self._on_task_exception)

        # Set running state
        self.tasks[task_id]._state = 'RUNNING'

    # Reload a tasks data by stopping/re-init-ing/starting
    def _reload_task(self, task_id):
        self.logger.debug('Reloading task: {0}'.format(task_id))
        self._stop_task(task_id)

        # Reload task data from Redis
        task_data = self.redis.hget('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id
        ), 'data')

        # Re-init & start the task
        self.tasks[task_id].__init__(**json.loads(task_data))
        self._start_task(task_id)

    # Restart failing tasks
    def _on_task_exception(self, greenlet):
        # Set task ERROR state
        print greenlet
        self.logger.critical('GREENLET EXCEPTION')

        # TODO: finish this

    # Check for new tasks in Redis
    def _get_new_tasks(self):
        new_task_id = self.redis.rpop(self.REDIS['NEW_QUEUE'])
        if new_task_id is not None:
            self._add_task(new_task_id)
            self._get_new_tasks()

    # Update RUNNING task times in Redis & cleanup old tasks
    def _update_tasks(self):
        print self.tasks

        # TODO: finish this


    ### Redis pubsub helpers
    # Check for Redis pubsub messages, apply to matching pattern/channel subscriptions
    def _pubsub(self):
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

    # Subscribe to Redis pubsub messages
    def _subscribe(self, callback, channel=None, pattern=None):
        if channel is not None:
            self.channel_subscriptions.setdefault(channel, []).append(callback)
            self.pubsub.subscribe(channel)

        if pattern is not None:
            self.pattern_subscriptions.setdefault(pattern, []).append(callback)
            self.pubsub.psubscribe(pattern)
