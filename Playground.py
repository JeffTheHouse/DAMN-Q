import numpy as np
from Operators import*
a = np.array([[.5,0,0,.5],
            [0,0,0,0],
            [0,0,0,0],
            [.5,0,0,.5]])

x = np.array([[a]])

b = np.array([[1,0],
            [0,0]])

print(f"Y = {np.dot(np.dot(x_operator, b), x_operator) }")




