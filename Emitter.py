from Scheduler import *

"""Process-wide default Simulation. Components use it unless given `sim=`."""
scheduler = Scheduler()


def _check_same_sim(src_sim, dst_sim, action="bind"):
    if src_sim is not None and dst_sim is not None and src_sim is not dst_sim:
        raise ValueError(
            f"Cannot {action} ports belonging to different Simulation instances."
        )


def _check_same_kind(src_kind, dst_kind, action="bind"):
    if src_kind is not None and dst_kind is not None and src_kind != dst_kind:
        raise ValueError(
            f"Cannot {action} incompatible port kinds: {src_kind!r} -> {dst_kind!r}."
        )


class Handler:
    def __init__(self, handler_func, sim=None, *, kind=None, max_connections=None):
        self._handler_func = handler_func
        if sim is None:
            owner = getattr(handler_func, "__self__", None)
            sim = getattr(owner, "sim", None)
        self.sim = sim
        self.kind = kind
        self.max_connections = max_connections
        self._emitters = []

    def handle(self, value):
        self._handler_func(value)


class Emitter:
    def __init__(self, sim=None, *, kind=None, max_connections=None):
        self._handlers = []
        self.sim = sim
        self.kind = kind
        self.max_connections = max_connections

    def emit(self, value):
        for handler in self._handlers:
            handler.handle(value)

    def add_handler(self, handler):
        if handler in self._handlers:
            raise ValueError("Duplicate connection between the same emitter and handler.")
        if self.max_connections is not None and len(self._handlers) >= self.max_connections:
            kind_label = f"{self.kind} " if self.kind else ""
            raise ValueError(
                f"Cannot fan out {kind_label}output port beyond max_connections={self.max_connections}."
            )
        dst_max = getattr(handler, "max_connections", None)
        dst_emitters = getattr(handler, "_emitters", None)
        if dst_max is not None and dst_emitters is not None and len(dst_emitters) >= dst_max:
            kind_label = f"{getattr(handler, 'kind', '')} " if getattr(handler, "kind", None) else ""
            raise ValueError(
                f"Cannot fan in to {kind_label}input port beyond max_connections={dst_max}."
            )
        self._handlers.append(handler)
        if dst_emitters is not None:
            dst_emitters.append(self)

    def remove_handler(self, handler):
        self._handlers.remove(handler)
        dst_emitters = getattr(handler, "_emitters", None)
        if dst_emitters is not None and self in dst_emitters:
            dst_emitters.remove(self)


def bind(emitter, handler):
    _check_same_sim(getattr(emitter, "sim", None), getattr(handler, "sim", None), "bind")
    _check_same_kind(getattr(emitter, "kind", None), getattr(handler, "kind", None), "bind")
    emitter.add_handler(handler)
