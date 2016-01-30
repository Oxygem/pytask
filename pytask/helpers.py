# pytask
# File: pytask/helpers.py
# Desc: helpers for interfacing with a pytask/Redis cluster

import json
from time import time
from uuid import uuid4

import gevent

from .redis_util import redis_clients, make_redis


def run_loop(function, interval):
    '''
    Like JavaScripts ``setInterval``, slight time drift as usual, useful in long running
    tasks.
    '''

    while True:
        before = time()
        function()

        duration = time() - before
        if duration < interval:
            gevent.sleep(interval - duration)


class _PyTaskRedisConf(object):
    def __init__(
        self, redis_instance,
        task_set='tasks', task_prefix='task-',
        new_queue='new-task', end_queue='end-task'
    ):
        # If redis_instance is a list, make a client
        if not isinstance(redis_instance, redis_clients):
            redis_instance = make_redis(redis_instance)

        self.redis = redis_instance

        self.TASK_SET = task_set
        self.TASK_PREFIX = task_prefix
        self.NEW_QUEUE = new_queue
        self.END_QUEUE = end_queue

    def task_key(self, task_id):
        return '{0}{1}'.format(self.TASK_PREFIX, task_id)

    def task_control(self, task_id):
        return '{0}{1}-control'.format(self.TASK_PREFIX, task_id)


class PyTaskHelpers(_PyTaskRedisConf):
    '''
    Helper functions for managing task data within Redis. All ``PyTask`` instances have
    an instance attached on their ``helpers`` attribute.

    Args:
        redis_instance (client or list): Redis client or list of ``(host, port)`` tuples
        task_set (str): name of task set
        task_prefix (str): prefix for task names
        new_queue (str): queue to read new task IDs from
        end_queue (str): where to push complete task IDs
    '''

    def get_new_task_ids(self):
        '''Get task IDs in the new queue.'''

        return self.redis.lrange(self.NEW_QUEUE, 0, -1)

    def get_end_task_ids(self):
        '''Get task IDs in the end queue.'''

        return self.redis.lrange(self.END_QUEUE, 0, -1)

    def get_active_task_ids(self):
        '''Get a list of active ``task_ids``.'''

        return list(self.redis.smembers(self.TASK_SET))

    def get_task(self, task_id, keys=None):
        '''Get task hash data.'''

        task_key = self.task_key(task_id)

        if keys:
            # Getting a single has key
            if isinstance(keys, basestring):
                return self.redis.hget(task_key, keys)

            # Multiple hash keys, returned in order
            return self.redis.hmget(task_key, keys)

        else:
            # The whole hash object, as dict
            return self.redis.hgetall(task_key)

    def set_task(self, task_id, data, value=None):
        '''Set task hash data.'''

        if value:
            self.redis.hset(self.task_key(task_id), data, value)
        else:
            self.redis.hmset(self.task_key(task_id), data)

    def reload_task(self, task_id):
        '''Reload a task.'''

        self.redis.publish(self.task_control(task_id), 'reload')

    def stop_task(self, task_id):
        '''Stop a task.'''

        self.redis.publish(self.task_control(task_id), 'stop')

    def restart_task(self, task_id):
        self.redis.lpush(self.NEW_QUEUE, task_id)

    def restart_if_state(self, task_id, states):
        state = self.get_task(task_id, 'state')

        if state in states:
            self.restart_task(task_id)

    def remove_task(self, task_id):
        # Delete from the set
        self.redis.srem(self.TASK_SET, task_id)

        # Remove the hash
        self.redis.delete(self.task_key(task_id))

    def start_task(self, task_name, task_id=None, cleanup=True, **task_data):
        '''Start a new task.'''

        # task_id None implies a short running task, thus no option in start_update
        if task_id is None:
            task_id = str(uuid4())

        # Make data JSON encoded
        task_data = json.dumps(task_data)

        task = {
            'task': task_name,
            'data': task_data,
            'state': 'WAIT'
        }

        if not cleanup:
            task['cleanup'] = 'false'

        # Add the task & data to the task hash
        self.set_task(task_id, task)

        # Push the task ID to the new queue if not already present - this requires a scan
        # of the entire new queue, so hopefully it's smallish.
        new_tasks = self.redis.lrange(self.NEW_QUEUE, 0, -1)
        if task_id not in new_tasks:
            self.redis.lpush(self.NEW_QUEUE, task_id)

        return task_id
