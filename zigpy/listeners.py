from __future__ import annotations

import asyncio
import dataclasses
import inspect
import logging
import typing

from zigpy.util import Singleton
from zigpy.zcl import foundation
import zigpy.zdo.types as zdo_t

LOGGER = logging.getLogger(__name__)


ANY_DEVICE = Singleton("ANY_DEVICE")


@dataclasses.dataclass(frozen=True)
class BaseRequestListener:
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
            match = None
            is_matcher_cmd = isinstance(matcher, foundation.CommandSchema)

            if is_matcher_cmd and isinstance(command, foundation.CommandSchema):
                match = command.matches(matcher)
            elif is_matcher_cmd and isinstance(hdr, zdo_t.ZDOHeader):
                # FIXME: ZDO does not use command schemas and cannot be matched
                pass
            elif callable(matcher):
                match = matcher(hdr, command)
            else:
                LOGGER.warning(
                    "Matcher %r and command %r %r are incompatible",
                    matcher,
                    hdr,
                    command,
                )

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

        raise NotImplementedError  # pragma: no cover

    def cancel(self):
        """Implement by subclasses to cancel the listener.

        Return value indicates whether or not the listener is cancelable.
        """

        raise NotImplementedError  # pragma: no cover


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
    _tasks: set[asyncio.Task] = dataclasses.field(default_factory=set)

    def _resolve(
        self,
        hdr: foundation.ZCLHeader | zdo_t.ZDOHeader,
        command: foundation.CommandSchema,
    ) -> bool:
        try:
            potential_awaitable = self.callback(hdr, command)
            if inspect.isawaitable(potential_awaitable):
                task: asyncio.Task = asyncio.get_running_loop().create_task(
                    potential_awaitable, name="CallbackListener"
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.remove)
        except Exception:  # noqa: BLE001
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
