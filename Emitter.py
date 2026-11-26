from Scheduler import *

"""Process-wide default Simulation. Components use it unless given `sim=`."""
scheduler = Scheduler()


def _check_same_sim(src_sim, dst_sim, action="bind"):
    if src_sim is not None and dst_sim is not None and src_sim is not dst_sim:
        raise ValueError(
            f"Cannot {action} ports belonging to different Simulation instances."
        )


class Handler:
    def __init__(self, handler_func, sim=None):
        self._handler_func = handler_func
        if sim is None:
            owner = getattr(handler_func, "__self__", None)
            sim = getattr(owner, "sim", None)
        self.sim = sim

    def handle(self, value):
        self._handler_func(value)


class Emitter:
    def __init__(self, sim=None):
        self._handlers = []
        self.sim = sim

    def emit(self, value):
        for handler in self._handlers:
            handler.handle(value)

    def add_handler(self, handler):
        self._handlers.append(handler)

    def remove_handler(self, handler):
        self._handlers.remove(handler)


def bind(emitter, handler):
    _check_same_sim(getattr(emitter, "sim", None), getattr(handler, "sim", None), "bind")
    emitter.add_handler(handler)
