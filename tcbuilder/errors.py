class TorizonCoreBuilderError(Exception):     
    def __init__(self, msg, deb_details=None, status_code=None, payload=None):
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

class IntegrityCheckFailed(TorizonCoreBuilderError):
    pass

class GitRepoError(TorizonCoreBuilderError):
    pass

class InvalidArgumentError(TorizonCoreBuilderError):
    pass

class InvalidStateError(TorizonCoreBuilderError):
    pass

class InvalidDataError(TorizonCoreBuilderError):
    pass

class FeatureNotImplementedError(TorizonCoreBuilderError):
    pass

class UserAbortError(TorizonCoreBuilderError):        
    def __init__(self, deb_details=None, status_code=None, payload=None):
        super().__init__("User aborted operation.",
                         deb_details=deb_details,status_code=status_code, payload=payload)

class InvalidAssignmentError(TorizonCoreBuilderError):
    pass
