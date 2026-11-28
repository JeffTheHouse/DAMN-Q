from Emitter import*
from Link import*


def connect(source, destination, delay = 0, loss_p = 0, depolarization_p = 0, sim=None, *, activity=None):
    """Bind source -> Link -> destination within one Simulation.

    Enforces simulation match, port kind compatibility, and port fan-out/fan-in
    limits atomically so a rejected connection leaves neither port mutated.
    """
    src_sim = getattr(source, "sim", None)
    dst_sim = getattr(destination, "sim", None)
    sims = [s for s in (src_sim, dst_sim, sim) if s is not None]
    if any(s is not sims[0] for s in sims[1:]):
        raise ValueError(
            "Cannot connect ports belonging to different Simulation instances."
        )

    src_kind = getattr(source, "kind", None)
    dst_kind = getattr(destination, "kind", None)
    if src_kind is not None and dst_kind is not None and src_kind != dst_kind:
        raise ValueError(
            f"Cannot connect incompatible port kinds: {src_kind!r} -> {dst_kind!r}."
        )
    link_kind = src_kind or dst_kind

    # Pre-check destination fan-in before mutating source
    dst_max = getattr(destination, "max_connections", None)
    dst_emitters = getattr(destination, "_emitters", None)
    if dst_max is not None and dst_emitters is not None and len(dst_emitters) >= dst_max:
        kind_label = f"{dst_kind} " if dst_kind else ""
        raise ValueError(
            f"Cannot fan in to {kind_label}input port beyond max_connections={dst_max}."
        )

    # Pre-check duplicate logical edge (source -> Link -> destination)
    for existing in getattr(source, "_handlers", ()):
        owner = getattr(getattr(existing, "_handler_func", None), "__self__", None)
        if isinstance(owner, Link) and destination in getattr(owner.ch_out, "_handlers", ()):
            raise ValueError("Duplicate connection between the same source and destination ports.")

    link_sim = sims[0] if sims else scheduler
    link = Link(
        link_sim.next_link_id(),
        delay,
        depolarization_p,
        loss_p,
        sim=link_sim,
        kind=link_kind,
        activity=activity,
    )
    bind(source, link.ch_in)
    try:
        bind(link.ch_out, destination)
    except Exception:
        source.remove_handler(link.ch_in)
        raise
