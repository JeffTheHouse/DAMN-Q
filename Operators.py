import numpy as np
"""Pauli's"""
x_operator = np.array([[0, 1], [1, 0]])
z_operator = np.array([[1, 0], [0, -1]])
y_operator = np.array([[0, -1j], [1j, 0]])
i_operator = np.identity(2)
h_operator = (1/np.sqrt(2)) * np.array([[1 , 1],[1 , -1]])

x_y_z_sum = x_operator + y_operator + z_operator



