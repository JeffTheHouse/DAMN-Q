class Id_generator:
    def __init__(self):
        self.current = 0
    
    def generate(self):
        id = self.current
        self.current +=1
        return id