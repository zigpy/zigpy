class ZigbeeException(Exception):
    """Base exception class"""


class ControllerException(ZigbeeException):
    """Application controller failed in some way."""


class APIException(ZigbeeException):
    """Radio API failed in some way."""


class DeliveryError(ZigbeeException):
    """Message delivery failed in some way"""

    def __init__(self, message: str, status=None):
        super().__init__(message)
        self.status = status


class InvalidResponse(ZigbeeException):
    """A ZDO or ZCL response has an unsuccessful status code"""


class RadioException(Exception):
    """Base exception class for radio exceptions"""


class NetworkNotFormed(RadioException):
    """A network cannot be started because the radio has no stored network info"""


class FormationFailure(RadioException):
    """Network settings could not be written to the radio"""


class NetworkSettingsInconsistent(ZigbeeException):
    """Loaded network settings are different from what is in the database"""
