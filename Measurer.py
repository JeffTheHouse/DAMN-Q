from Emitter import*
from Measurment_module import*
from Id_generator import*
import numpy as np
import random

class Measuring_Device:
    def __init__(self, id, delay, x_basis_p = 0, p_depolarization = 0):
        self.id = id
        self.delay = delay
        self.p_depolarization_depolarization= p_depolarization
        self.x_basis_p = x_basis_p
        self.in_ch = Handler(self.handle)
        self.id_generator_measurement = Id_generator()
        

    def handle(self, qubit):
        print(f"measurer: {self.id}")
        if qubit.state != None:
            result = measure(self.id_generator_measurement.generate(), qubit, self.x_basis_p)
            scheduler.add( self.delay, lambda: print(f"the result is {result.result}"))
        else:
            scheduler.add(self.delay, lambda: print(f"Qubit went missing in measurer {self.id}"))


"""# Density matrix of the qubit
rho = np.array([[1, 0], [0, 0]])

# Projectors for the computational basis
proj_0 = np.array([[1, 0], [0, 0]])
proj_1 = np.array([[0, 0], [0, 1]])

# Calculate probabilities of each outcome
prob_0 = np.trace(np.matmul(rho, proj_0))
prob_1 = np.trace(np.matmul(rho, proj_1))

print("Density matrix of the qubit:")
print(rho)
print("\nProbabilities of measurement outcomes:")
print(f"P(|0⟩) = {prob_0}")
print(f"P(|1⟩) = {prob_1}")

# Perform the measurement
if random.random() < prob_0:
    print("\nMeasurement outcome: |0⟩")
    rho = proj_0
else:
    print("\nMeasurement outcome: |1⟩")
    rho = proj_1

print("\nDensity matrix after measurement:")
print(rho)"""