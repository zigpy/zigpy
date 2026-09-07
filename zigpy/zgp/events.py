"""Event dataclasses emitted by :class:`zigpy.zgp.manager.GreenPowerManager`.

Subscribers register via :meth:`zigpy.event.EventBase.on_event` with the
matching :data:`event_type` string. Keeping the payload in a frozen
dataclass (rather than positional arguments on ``listener_event``) makes
the contract explicit and easier to extend without breaking callers.
"""

from __future__ import annotations

import dataclasses
from typing import Final

import zigpy.types as t
from zigpy.zgp.types import GPDCommandID


@dataclasses.dataclass(kw_only=True, frozen=True)
class DeviceJoined:
    """A new Green Power device was commissioned."""

    event_type: Final[str] = "gp_device_joined"

    device_ieee: str


@dataclasses.dataclass(kw_only=True, frozen=True)
class DeviceLeft:
    """A commissioned Green Power device was decommissioned or removed."""

    event_type: Final[str] = "gp_device_left"

    device_ieee: str


@dataclasses.dataclass(kw_only=True, frozen=True)
class CommandReceived:
    """A GPDF carrying an operational command was received and parsed.

    A subscriber can rely on ``payload`` always being the structured object
    from ``zigpy.zgp.commands``, never raw bytes; see ``RawCommandReceived``
    for the fallback case.
    """

    event_type: Final[str] = "gp_command_received"

    device_ieee: str
    command_id: GPDCommandID
    payload: t.Struct


@dataclasses.dataclass(kw_only=True, frozen=True)
class RawCommandReceived:
    """A GPDF command whose payload could not be parsed into a structured object.

    Emitted instead of ``CommandReceived`` when ``GPD_COMMAND_SCHEMAS`` has no
    entry for the command ID, or when the mapped schema fails to deserialize
    the payload. Adding a schema for a command in ``zigpy.zgp.commands``
    moves it from this event to ``CommandReceived``.
    """

    event_type: Final[str] = "gp_raw_command_received"

    device_ieee: str
    command_id: GPDCommandID
    payload: bytes
