from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    import zigpy.backups


class ZigbeeException(Exception):
    """Base exception class"""


class ParsingError(ZigbeeException):
    """Failed to parse a frame"""


class ControllerException(ZigbeeException):
    """Application controller failed in some way."""


class APIException(ZigbeeException):
    """Radio API failed in some way."""


class DeliveryError(ZigbeeException):
    """Message delivery failed in some way"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class SendError(DeliveryError):
    """Message could not be enqueued."""


class InvalidResponse(ZigbeeException):
    """A ZDO or ZCL response has an unsuccessful status code"""


class RadioException(Exception):
    """Base exception class for radio exceptions"""


class TransientConnectionError(RadioException):
    """Connection to the radio failed but will likely succeed in the near future"""


class NetworkNotFormed(RadioException):
    """A network cannot be started because the radio has no stored network info"""


class FormationFailure(RadioException):
    """Network settings could not be written to the radio"""


class NetworkSettingsInconsistent(ZigbeeException):
    """Loaded network settings are different from what is in the database"""

    def __init__(
        self,
        message: str,
        new_state: zigpy.backups.NetworkBackup,
        old_state: zigpy.backups.NetworkBackup,
    ) -> None:
        super().__init__(message)
        self.new_state = new_state
        self.old_state = old_state


class CorruptDatabase(ZigbeeException):
    """The SQLite database is corrupt or otherwise inconsistent"""


class QuirksException(Exception):
    """Base exception class"""


class MultipleQuirksMatchException(QuirksException):
    """Thrown when multiple v2 quirks match a device"""
