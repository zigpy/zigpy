"""Helper objects for zigpy."""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING

from typing_extensions import Self

import zigpy.types as t

if TYPE_CHECKING:
    from zigpy.application import ControllerApplication


class PacketCaptureManager:
    """Packet capture manager."""

    def __init__(self, app: ControllerApplication, channel: int) -> None:
        """Initializer."""
        self.app = app
        self.channel = channel
        self._packet_capture = None

    async def __aenter__(self) -> Self:
        """Enter the context manager."""
        self._packet_capture = self.app._packet_capture(channel=self.channel)
        return self

    def __aiter__(self) -> Self:
        """Get the next packet."""
        return self

    async def __anext__(self) -> t.CapturedPacket:
        """Get the next packet."""
        packet = await self._packet_capture.__anext__()

        if not packet.channel:
            packet = packet.replace(channel=self.channel)

        return packet

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the context manager."""
        await self._packet_capture.aclose()

    async def change_channel(self, channel: int) -> None:
        """Change the channel."""
        if channel == self.channel:
            return

        await self.app._packet_capture_change_channel(channel=channel)
        self.channel = channel
