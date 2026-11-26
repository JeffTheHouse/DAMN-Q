from Emitter import*
from Link import*


def connect(source, destination, delay = 0, loss_p = 0, depolarization_p = 0, sim=None):
    """Bind source -> Link -> destination within one Simulation.

    Raises ValueError if source, destination, or explicit `sim` belong to
    different Simulation instances.
    """
    src_sim = getattr(source, "sim", None)
    dst_sim = getattr(destination, "sim", None)
    sims = [s for s in (src_sim, dst_sim, sim) if s is not None]
    if any(s is not sims[0] for s in sims[1:]):
        raise ValueError(
            "Cannot connect ports belonging to different Simulation instances."
        )
    link_sim = sims[0] if sims else scheduler
    link = Link(link_sim.next_link_id(), delay, depolarization_p, loss_p, sim=link_sim)
    bind(source, link.ch_in)
    bind(link.ch_out, destination)
