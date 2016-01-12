# pytask
# File: pytask/tasks.py
# Desc: monitoring and cleanup tasks designed to keep a pytask cluster in shape

import logging

import gevent

from .pytask import Task
from .helpers import run_loop


class Monitor(Task):
    '''
    A pytask which monitors pytasks! Checks all task state in Redis at a configured
    interval, will re-queue tasks which timeout.
    '''

    NAME = 'pytask/monitor'

    def __init__(self, **task_data):
        self.loop_interval = task_data.get('loop_interval', 10)
        self.task_timeout = task_data.get('task_timeout', 60)

        self.logger = logging.getLogger('pytask-monitoring')

    def start(self):
        self.loop = gevent.spawn(run_loop, self.check_tasks, self.loop_interval)
        self.loop.join()

    def stop(self):
        self.loop.kill()

    def check_tasks(self):
        self.logger.info('Checking tasks...')


class Cleanup(Task):
    '''
    A pytask which cleans up other pytasks! Checks all task state in Redis at configured
    interval, removing where required.
    '''

    NAME = 'pytask/cleanup'

    def __init__(self, **task_data):
        self.loop_interval = task_data.get('loop_interval', 60)
        self.task_timeout = task_data.get('task_timeout', 60)

        self.logger = logging.getLogger('pytask-cleaning')

    def start(self):
        self.loop = gevent.spawn(run_loop, self.cleanup_tasks, self.loop_interval)
        self.loop.join()

    def stop(self):
        self.loop.kill()

    def cleanup_tasks(self):
        self.logger.info('Cleaning tasks...')
