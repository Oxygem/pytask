# pytask
# File: example/tasks/hello_world.py
# Desc: a simple hello world printing task

from .pytask import Task


class HelloWorld(Task):
    NAME = 'hello_world'

    def __init__(self, **task_data):
        self.text = task_data.pop('text', 'world')

    def start(self):
        print 'HELLO {}'.format(self.text)
