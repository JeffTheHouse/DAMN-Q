import numpy as np
import random
from Operators import*
from Data import*

def measure (measurement_id , qubit, x_basis_p):
    if random.random() <= x_basis_p:
        qubit.state.density_operator = np.kron(h_operator,i_operator) * qubit.state.density_operator * np.kron(h_operator,i_operator)
    shape = np.shape(qubit.state.density_matrix) [0]
    preivious_value = 0
    random_number = random.random()
    print(f"the recieved qubit: {qubit.state.density_matrix}")
    for i in range(shape):
        if preivious_value < random_number <= (preivious_value + qubit.state.density_matrix [i][i]):
            binary_representation = bin(i)[2:].zfill(2)
            print(f"binary representaion: {binary_representation}")
            measurement_output = Measurement_output(measurement_id, binary_representation [1])
            qubit.state.density_matrix = np.zeros((int(np.sqrt(shape)),int(np.sqrt(shape))))
            qubit.state.density_matrix [int(binary_representation[0])][int(binary_representation[0])] = 1

            return (measurement_output)
        else:
            preivious_value += qubit.state.density_matrix [i][i]