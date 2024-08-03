from Scheduler import*
from Emitter import*
from Measurer_memory_paired import*
from Measurer import*
from Link import*
from Pauli_corrector import*
from Source import*
from Entanglment_swapping_module import*
from Orchestrator import*
from Memory import*
from Auto_connector import*

source_a = Source(1,1,2)
source_b = Source(2,1,2)

memory_a_1 = Quantum_memory(1,0,0,100)
memory_a_2 = Quantum_memory(2,0,0,100)
memory_b_1 = Quantum_memory(3,1,0,100)
memory_b_2 = Quantum_memory(4,1,0,100)

es = Entaglment_swapping_module(1, 1)
orchestrator = Orchestrator(1,0)

pc = Pauli_corrector(1,0)
m_1 = Measurer_memory_paired(1,0,0,0)
m_2 = Measuring_Device(2,0,0,0)

"""Qubit routs: source and memory connections"""
connect(source_a.out_ch_1, memory_a_1.ch_in_q, 1)
connect(source_a.out_ch_2, memory_a_2.ch_in_q, 1)
connect(source_b.out_ch_1, memory_b_1.ch_in_q, 1)
connect(source_b.out_ch_2, memory_b_2.ch_in_q, 1)
"""Qubit routs: measurers and pauli corrector rout"""
connect(memory_a_1.ch_out_q, m_1.ch_in_q, 1)
connect(memory_b_2.ch_out_q, pc.ch_in_q, 1)
connect(pc.ch_out_q, m_2.in_ch, 1)
"""Qubit routs: memories and entanglment-swapper"""
connect(memory_a_2.ch_out_q, es.ch_in_q_1, 1)
connect(memory_b_1.ch_out_q, es.ch_in_q_2, 1)
"""Classic communication: Orchestrator and memories"""
connect(memory_a_2.ch_out_c, orchestrator.ch_in_memory_1)
connect(memory_b_1.ch_out_c, orchestrator.ch_in_memory_2)
"""Classic communication: entanglement-swapper, measurer and pauli corrector"""
connect(es.ch_out_c_1, m_1.ch_in_es)
connect(es.ch_out_c_2, pc.ch_in_es)
"""Classic communication: memories"""
connect(memory_a_1.ch_out_paired_memory, memory_a_2.ch_in_paired_memory)
connect(memory_a_2.ch_out_paired_memory, memory_a_1.ch_in_paired_memory)
connect(memory_b_1.ch_out_paired_memory, memory_b_2.ch_in_paired_memory)
connect(memory_b_2.ch_out_paired_memory, memory_b_1.ch_in_paired_memory)
"""Classic communication: measurer and memory"""
connect(memory_a_1.ch_out_c, m_1.ch_in_memory_c)
connect(m_1.ch_out_memory_c, memory_a_1.ch_in_c)
"""Classic communication: Pauli corrector and memory"""
connect(memory_b_2.ch_out_c, pc.ch_in_memory)
connect(pc.ch_out_memory, memory_b_2.ch_in_c)

scheduler.run(10)







