from Scheduler import*
from Emitter import*
from Qubits import*
from Measurer import*
from Source import*
from Link import*

source = Source(1, 1, 2)
link_1 = Link (1, 1, 0)
link_2 = Link(2, 2, 0)
measurer_1 = Measuring_Device(1, 0)
measurer_2 = Measuring_Device(2, 0)

bind(source.out_ch_1, link_1.ch_in)
bind(source.out_ch_2, link_2.ch_in)
bind(link_1.ch_out, measurer_1.in_ch)
bind(link_2.ch_out, measurer_2.in_ch)

scheduler.run(10)
