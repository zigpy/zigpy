from __future__ import annotations

import enum
import typing

if typing.TYPE_CHECKING:
    import zigpy.backups


class ZigbeeException(Exception):
    """Base exception class"""


class ParsingError(ZigbeeException):
    """Failed to parse a frame"""


class ControllerException(ZigbeeException):
    """Application controller failed in some way."""


class CannotWriteNetworkSettings(ZigbeeException):
    """The provided network settings cannot be written due to a radio limitation."""


class DestructiveWriteNetworkSettings(ZigbeeException):
    """The provided network settings will be written but in a destructive manner."""


class APIException(ZigbeeException):
    """Radio API failed in some way."""


class DeliveryError(ZigbeeException):
    """Message delivery failed in some way"""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class MacNoAckError(DeliveryError):
    """The next hop (or the destination, if direct) did not MAC-acknowledge the frame."""


class CcaFailureError(DeliveryError):
    """The frame was not transmitted: clear channel assessment failed (RF interference)."""


class ApsNoAckError(DeliveryError):
    """The destination did not send an end-to-end APS acknowledgment."""


class NoRouteError(DeliveryError):
    """No route to the destination exists and route discovery failed."""


class TransactionExpiredError(DeliveryError):
    """The frame expired at the parent before the sleepy destination polled for it."""


class SendError(DeliveryError):
    """Message could not be enqueued: the frame never left the radio."""


class PermanentSendError(SendError):
    """The frame cannot be sent as-is and retrying will not help."""


class FailureScope(enum.Enum):
    """What a transient send failure applies to."""

    # The radio or the channel as a whole: no send will currently succeed
    GLOBAL = "global"
    # Only sends to this frame's destination are affected
    DESTINATION = "destination"


class TransientSendError(SendError):
    """The radio temporarily cannot accept the frame, it can be retried later."""

    def __init__(
        self,
        message: str,
        status: int | None = None,
        *,
        scope: FailureScope = FailureScope.GLOBAL,
        retry_in: float | None = None,
    ):
        super().__init__(message, status)
        self.scope = scope
        self.retry_in = retry_in


class RadioBusyError(TransientSendError):
    """The radio's transmit queue, message table, or buffer pool is full."""


class NetworkBusyError(TransientSendError):
    """The RF channel or the mesh is congested."""


class SendCancelledError(SendError):
    """The send was cancelled before its frame left the radio."""


class SupersededError(SendCancelledError):
    """The send was replaced by a newer one with the same coalescing key."""


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
