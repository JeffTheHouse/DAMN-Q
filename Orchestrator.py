from Emitter import*
from Scheduler import*

class Orchestrator:
    def __init__(self, id, delay = 0):
        self.id = id
        self.delay = delay
        self.ch_in_memory_1 = Handler(self.handle_memory_1)
        self.ch_in_memory_2 = Handler(self.handle_memory_2)
        self.ch_out_memory_1 = Emitter()
        self.ch_out_memory_2 = Emitter()
        self.counter_memory_1 = 0
        self.counter_memory_2 = 0
        



    def handle_memory_1(self, message):
        self.counter_memory_1 += message
        self.coppler()

    def handle_memory_2(self, message):
        self.counter_memory_2 += message
        self.coppler()
            
    def coppler(self, ch_in_number):
        if self.counter_memory_1 != 0 and self.counter_memory_2 != 0:
            self.counter_memory_1 -=1
            self.counter_memory_2 -=1
            scheduler.add(0, lambda: self.ch_out_memory_1.emit(1))
            scheduler.add(0, lambda: self.ch_out_memory_2.emit(1))

