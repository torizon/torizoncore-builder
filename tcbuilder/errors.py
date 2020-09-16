class TorizonCoreBuilderError(Exception):
    def __init__(self, msg, deb_details=None,  status_code=None, payload=None):
        self.msg = msg
        self.det = deb_details
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

        super().__init__(self.msg)


class PathNotExistError(TorizonCoreBuilderError):
    pass

class OperationFailureError(TorizonCoreBuilderError):
    pass

class FileContentMissing(TorizonCoreBuilderError):
    pass

class GitRepoError(TorizonCoreBuilderError):
    pass