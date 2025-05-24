"""Helper objects for zigpy types."""

from __future__ import annotations

from enum import IntFlag


class UniqueIntFlag(IntFlag):
    """Mixin to ensure `Flag` members are unique."""

    def __init_subclass__(cls, *args, **kwargs):
        """Initialize the class and ensure `Flag` members are unique."""
        super().__init_subclass__(*args, **kwargs)

        for member in cls.__members__.values():
            n = int(member)

            if n != 0 and n & (n - 1) != 0:
                raise TypeError(
                    f"Flag {member.name} in {cls.__name__} must be a power of 2"
                )
