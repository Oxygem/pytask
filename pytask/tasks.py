# pytask
# File: pytask/tasks.py
# Desc: monitoring and cleanup tasks designed to keep a pytask cluster in shape

import logging
from time import time

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

    def __init__(self, **task_data):
        self.loop_interval = task_data.get('loop_interval', 60)

        self.logger = logging.getLogger('pytask-cleaning')

    def start(self):
        self.loop = gevent.spawn(run_loop, self.cleanup_tasks, self.loop_interval)
        self.loop.get()

    def stop(self):
        self.loop.kill()

    def cleanup_tasks(self):
        self.logger.info('Cleaning tasks...')

        task_ids = self.helpers.get_task_ids()

        for task_id in task_ids:
            task = self.helpers.get_task(task_id)

            if not task:
                self.logger.critical(
                    'Removing task ID in set but no hash!: {0}'.format(task_id)
                )
                self.helpers.remove_task(task_id)
                continue

            state = task.get('state')
            if state != 'RUNNING':
                self.logger.warning(
                    'Task {0} is {1} but in the task set, removing ID from set'.format(
                        task_id, state
                    )
                )
                self.redis.srem(self.helpers.TASK_SET, task_id)
