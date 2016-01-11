# pytask
# File: example/tasks/loop.py
# Desc: a simple infinite looping task (& publishing messages to Redis pubsub)

from .pytask import Task, run_loop


class Loop(Task):
    NAME = 'loop'

    def __init__(self, **task_data):
        '''Setup task data.'''

        self.loop_interval = task_data.get('loop_interval', 10)

    def start(self):
        '''Spawn a loop to do some work on the interval.'''

        self.loop = run_loop(self.work, self.loop_interval)

    def stop(self):
        '''Stop the loop when requested.'''

        self.loop.kill()

    def work(self):
        '''Do some work.'''

        self.emit('text', self.task_data.get('text', 'Hello world'))
