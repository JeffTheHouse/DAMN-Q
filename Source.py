from Qubits import*
from Emitter import*
from Id_generator import*
from Hardware_models import werner_bell_density
class Source:
    def __init__(self, id, delay, type, sim=None, initial_fidelity=1.0):
        self.id = id
        if delay <= 0:
            raise ValueError("Source needs a delay bigger than zero!")
        else:
            self.delay = delay
        self.type = type
        if not (0.25 <= initial_fidelity <= 1.0):
            raise ValueError(f"initial_fidelity must be in [0.25, 1], got {initial_fidelity}")
        # Werner-state quality of emitted |Phi+> pairs (type 2); 1.0 is the ideal pair.
        self.initial_fidelity = float(initial_fidelity)
        self.sim = sim if sim is not None else scheduler
        self.id_generator = Id_generator()
        self.attempts = 0
        self.out_ch_1 = Emitter(sim=self.sim, kind="quantum", max_connections=1)
        self.out_ch_2 = Emitter(sim=self.sim, kind="quantum", max_connections=1)

        self.sim.add(self.delay, lambda:self.prepare())

    def prepare(self):
        pair_id = self.sim.next_pair_id()
        now = self.sim.time
        if self.type == 1:
            self.attempts += 1
            qubit = Qubit(
                self.id_generator.generate(),
                State(np.array([[1 , 0],[0 , 0]])),
                pair_id=pair_id,
                created_at=now,
            )
            self.out_ch_1.emit(qubit)
        elif self.type == 2:
            self.attempts += 1
            if self.initial_fidelity == 1.0:
                pair_state = State(np.array([[.5,0,0,.5],
                                [0,0,0,0],
                                [0,0,0,0],
                                [.5,0,0,.5]]))
            else:
                pair_state = State(werner_bell_density(self.initial_fidelity))
            qubit_1 , qubit_2 = Qubit.bell_state(
                self.id_generator.generate(),
                self.id_generator.generate(),
                pair_state,
                pair_id=pair_id,
                created_at=now,
            )

            self.out_ch_1.emit(qubit_1)
            self.out_ch_2.emit(qubit_2)
        else:
            print(f"error")

        self.sim.add(self.delay, lambda:self.prepare())
