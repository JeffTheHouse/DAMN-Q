from Qubits import*


"""qubit = Qubit(1, State((np.array([[1,0,0,1],
                                 [0,0,0,0],
                                 [0,0,0,0],
                                 [1,0,0,1]]))/2))
print(qubit.state.density_matrix)
print(f"the shape: {qubit.state.density_matrix.shape[0]}")
qubit.state.depolarizing_channel(.75)
print(f" aftermath: {qubit.state.density_matrix}")"""

qubit = Qubit(1, State(np.array([[1 , 0],[0 , 0]])))
print(qubit.state.density_matrix)
print(f"the shape: {qubit.state.density_matrix.shape[0]}")
qubit.state.depolarizing_channel(.75)
print(f" aftermath: {qubit.state.density_matrix}")