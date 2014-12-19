# pytask
# File: pytask.py
# Desc: provides a framework for managing & running greenlet based tasks

import sys
import time
import json
import logging
import traceback
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

    def emit(self, event, data):
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

    def pre_start_task(self, task_name, task_data=None):
        '''Used to start tasks on this worker (no queue), before calling .run'''
        if task_data is None:
            task_data = {}

        self.pre_start_tasks.append((task_name, task_data))

    def add_task(self, task_class):
        '''Add a task class'''
        self.TASKS[task_class.NAME] = task_class


    ### Internal task management
    def _pre_start_task(self, task_name, task_data):
        '''Starts a task on *this* worker'''
        # Generate task_id
        task_id = str(uuid4())

        # Write task hash to Redis
        self.redis.hmset('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id,
        ), {
            'task': task_name,
            'data': json.dumps(task_data)
        })

        # Add the task
        self._add_task(task_id)

    def _add_task(self, task_id):
        '''Interally add a task from the new-task queue'''
        self.logger.debug('New task: {0}'.format(task_id))

        # Check if task exists, exit if so (assume duplicate queue push)
        task_exists = self.redis.sismember(self.REDIS['TASK_SET'], task_id)
        if task_exists: return

        # Read the task hash
        task_class, task_data = self.redis.hmget('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id
        ), ['task', 'data'])

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
        task._redis = self.redis
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

        # Subscribe to control channel
        self._subscribe(
            lambda message: self._control_task(task_id, message),
            channel='{0}{1}-control'.format(
            self.REDIS['TASK_PREFIX'],
            task_id
        ))

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

        self.tasks[task_id].stop()
        self.greenlets[task_id].kill()
        del self.greenlets[task_id]

        # Set STOPPED in task & Redis
        self.tasks[task_id]._state = 'STOPPED'
        self.redis.hset('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id,
        ), 'state', 'STOPPED')

    def _start_task(self, task_id):
        '''Starts a task in a new greenlet'''
        if self.tasks[task_id]._state == 'RUNNING': return

        self.logger.debug('Starting task: {0}'.format(task_id))
        def wrapper():
            try:
                self.tasks[task_id].start()
            except Exception as e:
                self._on_task_exception(task_id, e)

        self.greenlets[task_id] = gevent.spawn(wrapper)

        # Set running state
        self.tasks[task_id]._state = 'RUNNING'
        self.redis.hset('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id,
        ), 'state', 'RUNNING')

    def _reload_task(self, task_id):
        '''Reload a tasks data by stopping/re-init-ing/starting'''
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

    def _on_task_exception(self, task_id, e):
        '''Restart failing tasks'''
        # Get the error details
        error_type, value, trace = sys.exc_info()
        self.logger.warning('Exception in task: {0}: {1} - {2}'.format(task_id, error_type.__name__, e))
        print '------------ Traceback:'
        print traceback.print_tb(trace)
        print '------------'

        # Set error state
        self.tasks[task_id]._state = 'ERROR'
        self.redis.hset('{0}{1}'.format(
            self.REDIS['TASK_PREFIX'],
            task_id,
        ), 'state', 'ERROR')

    def _get_new_tasks(self):
        '''Check for new tasks in Redis'''
        new_task_id = self.redis.rpop(self.REDIS['NEW_QUEUE'])
        if new_task_id is not None:
            self._add_task(new_task_id)
            self._get_new_tasks()

    def _update_tasks(self):
        '''Update RUNNING task times in Redis'''
        update_time = time.time()

        for task_id, task in self.tasks.iteritems():
            if task._state == 'RUNNING':
                self.redis.hset('{}{}'.format(
                    self.REDIS['TASK_PREFIX'],
                    task_id
                ), 'last_update', update_time)

        # TODO: cleanup tasks


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
