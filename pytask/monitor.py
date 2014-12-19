# pytask
# File: monitor.py
# Desc: a monitoring task to watch for and requeue dead tasks

from .pytask import Task, run_loop


class Monitor(Task):
    '''
    A pytask which monitors py tasks!
    Checks all task state in Redis at a configured interval, will re-queue tasks which timeout
    '''
    NAME = 'pytask/monitor'

    def __init__(self, **task_data):
        self.loop_interval = task_data.pop('loop_interval', 10)
        self.task_timeout = task_data.pop('task_timeout', 60)

    def start(self):
        run_loop(self.work, self.loop_interval)

    def work(self):
        print 'checking tasks...'
