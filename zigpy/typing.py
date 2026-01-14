"""Typing helpers for Zigpy."""

from __future__ import annotations

import enum

import zigpy.types as t


class UndefinedType(enum.Enum):
    """Singleton type for use with not set sentinel values."""

    _singleton = 0


UNDEFINED = UndefinedType._singleton  # noqa: SLF001


AddressingMode = t.AddrMode
