from Scheduler import*
from Emitter import*

class Test_source:
    def __init__(self, type):
        self.type = type
        self.in_channel_1 = Handler(self.handle)
        self.in_channel_2 = Handler(self.handle)

    def handle(self, qubit):
        
        if qubit.state is not None:
            print(f"Qubit {qubit.id} has the state of \n {qubit.state.density_matrix}")

        