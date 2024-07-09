from Scheduler import *

"""Scheduler is here!"""
scheduler = Scheduler()
class Handler:
    def __init__(self, handler_func):
        self._handler_func = handler_func

    def handle(self, value):
        self._handler_func(value)


class Emitter:
    def __init__(self):
        self._handlers = []

    def emit(self, value):
        for handler in self._handlers:
            handler.handle(value)

    def add_handler(self, handler):
        self._handlers.append(handler)

    def remove_handler(self, handler):
        self._handlers.remove(handler)



def bind(emitter, handler):
    emitter.add_handler(handler)