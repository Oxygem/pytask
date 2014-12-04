# pytask
# File: pytask.py
# Desc: provides a framework for managing & running greenlet based tasks

import time
import logging

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
    # Internal task state
    state = 'WAIT'

    # Emit task events
    def emit(self, event, data):
        pass


class PyTask(object):
    REDIS = None
    TASKS = {}

    # Default config
    # new_task_interval = when to check for new tasks (s)
    def __init__(self, redis_instance,
        task_set='tasks', new_queue='new-task', end_queue='end-task', task_prefix='task-',
        new_task_interval=1
    ):
        self.new_task_interval = new_task_interval
        self.logger = logging.getLogger('pytask')

        # Set Redis instance & config constants
        self.redis = redis_instance
        self.REDIS = {
            'TASK_SET': task_set,
            'NEW_QUEUE': new_queue,
            'END_QUEUE': end_queue,
            'TASK_PREFIX': task_prefix
        }

    # Stop a task (requested via pub/sub)
    def _stop_task(task_id):
        pass

    # Restart failing tasks
    def _on_task_exception(self, greenlet):
        print greenlet

    # Interally add a task from the new-task queue
    def _add_task(self, task_id):
        self.logger.debug('Adding task: {0}'.format(task_id))

        # Check if task exists, exit if so (assume duplicate queue push)
        task_exists = self.redis.sismember(self.REDIS['TASK_SET'], task_id)
        if task_exists: return

        # Read the task hash
        task_class, task_data = self.redis.hmget('{0}{1}'.format(self.REDIS['TASK_PREFIX'], task_id), ['function', 'data'])

        # Create task instance, assign it Redis
        task = self.TASKS[task_class](task_data)
        print task
        # Create greenlet

    def _get_new_tasks(self):
        new_task_id = self.redis.rpop(self.REDIS['NEW_QUEUE'])
        if new_task_id is not None:
            self._add_task(new_task_id)
            self._get_new_tasks()

    # Run pytask, basically a wrapper to handle tick count & KeyboardInterrupt
    def run(self, task_map):
        self.TASKS = task_map

        self.logger.debug('Starting up...')
        self.logger.debug('Loaded tasks: {0}'.format(self.TASKS.keys()))

        # Start the new_task loop
        new_task_loop = gevent.spawn(run_loop, self._get_new_tasks, self.new_task_interval)

        try:
            # If this ever returns, something broke...
            gevent.joinall([new_task_loop])
        except KeyboardInterrupt:
            # ... or the user/process asked us to quit!
            self.logger.info('Exiting upon user command...')
