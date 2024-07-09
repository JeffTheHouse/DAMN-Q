from queue import PriorityQueue, Empty
import itertools
import random
class Scheduler:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._queue = PriorityQueue()
            self._time = 0
            self._counter = itertools.count()
            self._initialized = True

    def add(self, delay, callback):
        item = (self._time + delay, next(self._counter), callback)
        self._queue.put(item)

    def run(self, until):
        step = until / 100
        next_step = 0
        try:
            while True:
                (time, _, callback) = self._queue.get(block=False)
                if time > next_step:
                    print(int(next_step), "/", until)
                    next_step += step
                if time > until:
                    return
                self._time = time
                callback()
        except Empty:
            pass

    def reset(self):
        self._queue = PriorityQueue()
        self._time = 0
