# pytask
# File: pytask/tasks.py
# Desc: monitoring and cleanup tasks designed to keep a pytask cluster in shape

import logging
from time import time
from importlib import import_module

import gevent

from .pytask import Task
from .helpers import run_loop


class Monitor(Task):
    '''
    A pytask which monitors pytasks! Checks all task state in Redis at a configured
    interval, will re-queue tasks which timeout.
    '''

    NAME = 'pytask/monitor'

    def __init__(self, loop_interval=10, task_timeout=60):
        self.loop_interval = loop_interval
        self.task_timeout = task_timeout

        self.logger = logging.getLogger('pytask-monitoring')

    def start(self):
        self.loop = gevent.spawn(run_loop, self.check_tasks, self.loop_interval)
        self.loop.get()

    def stop(self):
        self.loop.kill()

    def check_tasks(self):
        self.logger.info('Checking tasks...')

        task_ids = self.helpers.get_task_ids()

        for task_id in task_ids:
            task = self.helpers.get_task(task_id)

            if not task:
                self.logger.critical('Task ID in set but no hash!: {0}'.format(task_id))
                continue

            # Ensure running tasks are actually running
            if task.get('state') == 'RUNNING':
                update_time = task.get('last_update', 0)
                diff = time() - float(update_time)

                if diff > self.task_timeout:
                    # Local task that is still RUNNING, just remove/cleanup
                    if task.get('local') == 'true':
                        self.logger.info(
                            'Removing timed out local task: {0}'.format(task_id)
                        )
                        self.helpers.remove_task(task_id)

                    # Normal task, reset the state and restart it
                    else:
                        self.logger.warning(
                            'Restarting timed out task: {0}'.format(task_id)
                        )
                        self.helpers.set_task(task_id, 'state', 'WAIT')
                        self.helpers.restart_task(task_id)


class Cleanup(Task):
    '''
    A pytask which cleans up other pytasks! Checks all task state in Redis at configured
    interval, removing where required.
    '''

    NAME = 'pytask/cleanup'

    def __init__(self, task_handler=None):
        if task_handler:
            module, attr = task_handler.split(':')
            self.task_handler = getattr(import_module(module), attr)

        self.logger = logging.getLogger('pytask-cleaning')

    def start(self):
        while True:
            task_id = self.redis.brpop(self.helpers.END_QUEUE)
            task = self.helpers.get_task(task_id)

            self.logger.info('Cleaning {0} task: {1}'.format(task.get('state'), task_id))
            self.helpers.remove_task(task_id)

            if self.task_handler:
                self.task_handler(task_id, task)
