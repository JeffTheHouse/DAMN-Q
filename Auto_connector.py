from Emitter import*
from Link import*


def connect(source, destination, delay = 0, loss_p = 0, depolarization_p = 0, sim=None):
    """Bind source -> Link -> destination. Link IDs come from the simulation."""
    sim = sim if sim is not None else scheduler
    link = Link(sim.next_link_id(), delay, depolarization_p, loss_p, sim=sim)
    bind(source, link.ch_in)
    bind(link.ch_out, destination)
