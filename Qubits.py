import numpy as np
from Operators import*
from States import*
import random

class State:
    def __init__(self, density_matrix):
        self.density_matrix = density_matrix

    def depolarizing_channel(self, p):
        if np.shape(self.density_matrix) [0] == 4: 
            self.density_matrix = (1 - 4*p/3 ) * self.density_matrix + 4*p/3 * ((1/4) * np.identity(4))
        elif np.shape(self.density_matrix) [0] == 2:
            self.density_matrix = (1 - p) * self.density_matrix + p/3 * np.dot(x_y_z_sum, np.dot(self.density_matrix, x_y_z_sum))

    def loss_channel(self):
        if np.shape(self.density_matrix) [0] == 4:
            self.density_matrix = 1/2 * np.identity(2)
        
class Qubit:
    def __init__(self, id, state):
        self.id = id
        self.state = state

    @staticmethod
    def bell_state (id_1, id_2, state):
        qubit_1 = Qubit(id_1, state)
        qubit_2 = Qubit(id_2, state)

        return(qubit_1 , qubit_2)
    
    def loss(self, loss_p):
        if random.random() <= loss_p:
            self.state.loss_channel()
            self.state = None




    
            