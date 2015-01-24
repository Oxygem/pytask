# pytask
# File: example/tasks/loop.py
# Desc: a simple infinite looping task (& publishing messages to Redis pubsub)

import gevent

from .pytask import Task, run_loop


class Loop(Task):
    NAME = 'loop'

    def start(self):
        '''Spawn a loop to do some work on the interval'''
        self.loop = gevent.spawn(run_loop, self.work, self.task_data.get('loop_interval', 10))

    def stop(self):
        '''Stop the loop when requested'''
        self.loop.kill()

    def work(self):
        self.emit('text', self.task_data.get('text', 'Hello world'))
