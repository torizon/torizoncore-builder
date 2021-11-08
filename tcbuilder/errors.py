
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

class ParseError(TorizonCoreBuilderError):
    """Configuration file parsing error"""

    def __init__(self, msg, **kwargs):
        super().__init__(msg, **kwargs)
        # Extra attributes to hold information about where the parsing
        # error occurred.
        self.file = None
        self.line = None
        self.column = None
        self.prop = None

    def set_source(self, file=None, line=None, column=None, prop=None):
        """Set information about where a parsing error occurred"""
        self.file = file or self.file
        self.line = line or self.line
        self.column = column or self.column
        self.prop = prop or self.prop

    def __str__(self):
        parts = []
        if self.file:
            parts.append(self.file + ":")
        if self.line:
            parts.append(str(self.line) + ":")
        if self.column:
            parts.append(str(self.column) + ":")
        if parts:
            parts.append(" ")
        # Message must be always present:
        parts.append(self.msg)
        if self.prop is not None:
            # Format the property path like an XPath.
            path = '/'.join([str(prop) for prop in self.prop])
            parts.append(f", while parsing /{path}")
        return "".join(parts)


class ParseErrors(TorizonCoreBuilderError):
    """Configuration file parsing error with children"""


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
        super().__init__(
            "User aborted operation.",
            deb_details=deb_details, status_code=status_code, payload=payload)

class InvalidAssignmentError(TorizonCoreBuilderError):
    pass

class ImageUnpackError(TorizonCoreBuilderError):
    """
    Should be raised by commands that need an "images unpack" prior to their
    execution.
    """

    msg = ["Error: could not find an Easy Installer image in the storage.",
           "Please use the 'images' command to unpack an Easy Installer "
           "image before running this command."]

    def __init__(self):
        super().__init__(msg="\n".join(ImageUnpackError.msg))

class FetchError(TorizonCoreBuilderError):
    pass
