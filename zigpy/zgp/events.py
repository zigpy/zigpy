"""Event dataclasses emitted by :class:`zigpy.zgp.manager.GreenPowerManager`.

Subscribers register via :meth:`zigpy.event.EventBase.on_event` with the
matching :data:`event_type` string. Keeping the payload in a frozen
dataclass (rather than positional arguments on ``listener_event``) makes
the contract explicit and easier to extend without breaking callers.
"""

from __future__ import annotations

import dataclasses
from typing import Final

from zigpy.zgp.device import GPDevice
from zigpy.zgp.types import GPDCommandID


@dataclasses.dataclass(kw_only=True, frozen=True)
class DeviceJoined:
    """A new Green Power device was commissioned."""

    event_type: Final[str] = "gp_device_joined"

    device: GPDevice


@dataclasses.dataclass(kw_only=True, frozen=True)
class DeviceLeft:
    """A commissioned Green Power device was decommissioned or removed."""

    event_type: Final[str] = "gp_device_left"

    device: GPDevice


@dataclasses.dataclass(kw_only=True, frozen=True)
class CommandReceived:
    """A GPDF carrying an operational command was received."""

    event_type: Final[str] = "gp_command_received"

    device: GPDevice
    command_id: GPDCommandID
    payload: bytes
