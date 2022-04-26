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
