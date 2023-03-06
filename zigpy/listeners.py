from __future__ import annotations

import asyncio
import dataclasses
import logging
import typing

from zigpy.zcl import foundation
import zigpy.zdo.types as zdo_t

if typing.TYPE_CHECKING:
    import zigpy.device

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class BaseRequestListener:
    device: zigpy.device.Device
    matchers: tuple[MatcherType]

    def resolve(
        self,
        hdr: foundation.ZCLHeader | zdo_t.ZDOHeader,
        command: foundation.CommandSchema,
    ) -> bool:
        """Attempts to resolve the listener with a given response. Can be called with any
        command as an argument, including ones we don't match.
        """

        for matcher in self.matchers:
            if isinstance(matcher, foundation.CommandSchema) and isinstance(
                command, foundation.CommandSchema
            ):
                match = command.matches(matcher)
            else:
                match = matcher(hdr, command)

            if match:
                return self._resolve(hdr, command)

        return False

    def _resolve(
        self,
        hdr: foundation.ZCLHeader | zdo_t.ZDOHeader,
        command: foundation.CommandSchema,
    ) -> bool:
        """Implemented by subclasses to handle matched commands.

        Return value indicates whether or not the listener has actually resolved,
        which can sometimes be unavoidable.
        """

        raise NotImplementedError()  # pragma: no cover

    def cancel(self):
        """Implement by subclasses to cancel the listener.

        Return value indicates whether or not the listener is cancelable.
        """

        raise NotImplementedError()  # pragma: no cover


@dataclasses.dataclass(frozen=True)
class FutureListener(BaseRequestListener):
    future: asyncio.Future

    def _resolve(
        self,
        hdr: foundation.ZCLHeader | zdo_t.ZDOHeader,
        command: foundation.CommandSchema,
    ) -> bool:
        if self.future.done():
            return False

        self.future.set_result((hdr, command))
        return True

    def cancel(self):
        self.future.cancel()
        return True


@dataclasses.dataclass(frozen=True)
class CallbackListener(BaseRequestListener):
    callback: typing.Callable[
        [foundation.ZCLHeader | zdo_t.ZDOHeader, foundation.CommandSchema], typing.Any
    ]

    def _resolve(
        self,
        hdr: foundation.ZCLHeader | zdo_t.ZDOHeader,
        command: foundation.CommandSchema,
    ) -> bool:
        try:
            result = self.callback(hdr, command)

            # Run coroutines in the background
            if asyncio.iscoroutine(result):
                asyncio.create_task(result)
        except Exception:
            LOGGER.warning(
                "Caught an exception while executing callback", exc_info=True
            )

        # Callbacks are always resolved
        return True

    def cancel(self):
        # You can't cancel a callback
        return False


MatcherFuncType = typing.Callable[
    [
        typing.Union[foundation.ZCLHeader, zdo_t.ZDOHeader],
        foundation.CommandSchema,
    ],
    bool,
]
MatcherType = typing.Union[MatcherFuncType, foundation.CommandSchema]
