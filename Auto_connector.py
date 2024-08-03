from Emitter import*
from Link import*
from Id_generator import*

link_id_generator = Id_generator()

def connect(source, destination, delay = 0, loss_p = 0, depolarization_p = 0):
    link = Link(link_id_generator.generate(),delay,depolarization_p,loss_p)
    bind(source, link.ch_in)
    bind(link.ch_out, destination)
