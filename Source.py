from Qubits import*
from Emitter import*
from Id_generator import*
from Hardware_models import werner_bell_density
class Source:
    def __init__(self, id, delay, type, sim=None, initial_fidelity=1.0, emission_p=1.0):
        self.id = id
        if delay <= 0:
            raise ValueError("Source needs a delay bigger than zero!")
        else:
            self.delay = delay
        self.type = type
        if not (0.25 <= initial_fidelity <= 1.0):
            raise ValueError(f"initial_fidelity must be in [0.25, 1], got {initial_fidelity}")
        if not (0.0 < emission_p <= 1.0):
            raise ValueError(f"emission_p must be in (0, 1], got {emission_p}")
        # Werner-state quality of emitted |Phi+> pairs (type 2); 1.0 is the ideal pair.
        self.initial_fidelity = float(initial_fidelity)
        # Per-attempt emission probability (1.0 = deterministic, no extra RNG draw).
        self.emission_p = float(emission_p)
        self.sim = sim if sim is not None else scheduler
        self.id_generator = Id_generator()
        self.attempts = 0
        self.emitted = 0
        self.out_ch_1 = Emitter(sim=self.sim, kind="quantum", max_connections=1)
        self.out_ch_2 = Emitter(sim=self.sim, kind="quantum", max_connections=1)

        self.sim.add(self.delay, lambda:self.prepare())

    def prepare(self):
        if self.type not in (1, 2):
            print(f"error")
            self.sim.add(self.delay, lambda:self.prepare())
            return

        self.attempts += 1
        attempt_id = self.attempts
        if self.emission_p < 1.0 and self.sim.rng.random() >= self.emission_p:
            self.sim.add(self.delay, lambda:self.prepare())
            return

        pair_id = self.sim.next_pair_id()
        now = self.sim.time
        self.emitted += 1
        if self.type == 1:
            qubit = Qubit(
                self.id_generator.generate(),
                State(np.array([[1 , 0],[0 , 0]])),
                pair_id=pair_id,
                created_at=now,
            )
            qubit.attempt_id = attempt_id
            self.out_ch_1.emit(qubit)
        else:
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
            qubit_1.attempt_id = attempt_id
            qubit_2.attempt_id = attempt_id

            self.out_ch_1.emit(qubit_1)
            self.out_ch_2.emit(qubit_2)

        self.sim.add(self.delay, lambda:self.prepare())
