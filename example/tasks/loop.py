# pytask
# File: example/tasks/loop.py
# Desc: a simple infinite looping task (& publishing messages to Redis pubsub)

from .pytask import Task, run_loop


class Loop(Task):
    NAME = 'loop'

    def __init__(self, **task_data):
        self.loop_interval = task_data.pop('loop_interval', 10)
        self.text = task_data.pop('text', 'hello world')

    def start(self):
        run_loop(self.work, self.loop_interval)

    def work(self):
        self.emit('text', self.text)
