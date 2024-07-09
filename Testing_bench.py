from Qubits import*
from Source import*
from Measurer import*
from Link import*
from Test_source import*

tester = Test_source(2)
source = Source(1, 1, 1)
"""link_1 = Link(1, 1, .75)
link_2 = Link(2, 1, .75)
bind(source.out_ch_1, link_1.ch_in)
bind(source.out_ch_2, link_2.ch_in)
bind(link_1.ch_out, tester.in_channel_1)
bind(link_2.ch_out, tester.in_channel_2)
scheduler.run(100)"""
link = Link(1, 1, 0)
measurer = Measuring_Device(1, 1, 0)

bind(source.out_ch_1, link.ch_in)
bind(link.ch_out, measurer.in_ch)

scheduler.run(10)

