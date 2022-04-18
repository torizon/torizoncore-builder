class TeziError(Exception):
    """Base exception for Tezi errors"""
    def __init__(self, msg):
        self.msg = msg
        super().__init__(msg)

class SourceInFilelistError(TeziError):
    pass

class TargetInFilelistError(TeziError):
    pass

class InvalidDataError(TeziError):
    pass
