"""Mock utilities that are async aware."""
import sys

if sys.version_info[:2] < (3, 8):
    from asynctest.mock import *  # noqa
    from asynctest.mock import MagicMock as _MagicMock

    AsyncMock = CoroutineMock  # noqa: F405

    class MagicMock(_MagicMock):
        async def __aenter__(self):
            return self.aenter

        async def __aexit__(self, *args):
            pass

        async def __aiter__(self):
            return self.aiter

else:
    from unittest.mock import *  # noqa


class _IntSentinelObject(int):
    """
    Sentinel-like object that is also an integer subclass. Allows sentinels to be used
    in loggers that perform int-specific string formatting.
    """

    def __new__(cls, name):
        instance = super().__new__(cls, 0)
        instance.name = name
        return instance

    def __repr__(self):
        return "int_sentinel.%s" % self.name

    def __hash__(self):
        return hash((int(self), self.name))

    def __eq__(self, other):
        return self is other

    __str__ = __reduce__ = __repr__


class _IntSentinel:
    def __init__(self):
        self._sentinels = {}

    def __getattr__(self, name):
        if name == "__bases__":
            raise AttributeError
        return self._sentinels.setdefault(name, _IntSentinelObject(name))

    def __reduce__(self):
        return "int_sentinel"


int_sentinel = _IntSentinel()
