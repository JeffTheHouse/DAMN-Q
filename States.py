import numpy as np
phi_plus = 1/2 * np.array( [[1,0,0,1],
                            [0,0,0,0],
                            [0,0,0,0],
                            [1,0,0,1]])

phi_minus = 1/2 * np.array( [[1,0,0,-1],
                            [0,0,0,0],
                            [0,0,0,0],
                            [-1,0,0,1]])

psi_plus = 1/2 * np.array([[0, 0, 0, 0],
                            [0, 1, 1, 0],
                            [0, 1, 1, 0],
                            [0, 0, 0, 0]])

psi_minus = 1/2 * np.array([[0, 0, 0, 0],
                             [0, 1, -1, 0],
                             [0, -1, 1, 0],
                             [0, 0, 0, 0]])
