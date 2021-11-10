from __future__ import annotations

import asyncio
import logging
import time
import typing

import aiohttp

LOGGER = logging.getLogger(__name__)


class ExpiringCache:
    """
    Simple key/value cache with mandatory expiration.

    Note: not thread safe!
    Note: references to expired items are only cleaned on access. Periodically call
          `clean()` if this is a problem.
    """

    def __init__(self):
        self._cache: dict[typing.Hashable, typing.Any] = {}

    def get_with_expiration(self, key: typing.Hashable) -> tuple[float, typing.Any]:
        expires, value = self._cache[key]
        now = time.time()

        if expires <= now:
            del self._cache[key]
            raise KeyError(f"Key {key}!r expired {now - expires}s ago")

        return expires, value

    def expires(self, key: typing.Hashable) -> float:
        expires, _ = self.get_with_expiration(key)
        return expires

    def set(self, key: typing.Hashable, value: typing.Any, *, expire_in: float) -> None:
        if expire_in <= 0:
            return

        self._cache[key] = (time.time() + expire_in, value)

    def delete(self, key: typing.Hashable) -> None:
        self.get_with_expiration(key)  # To raise a `KeyError` when it already expired
        del self._cache[key]

    def clean(self):
        for key in tuple(self._cache.keys()):
            try:
                self[key]
            except KeyError:
                pass

    def __getitem__(self, key: typing.Hashable) -> typing.Any:
        _, value = self.get_with_expiration(key)
        return value

    def __contains__(self, key: typing.Hashable) -> bool:
        try:
            self.get_with_expiration(key)
        except KeyError:
            return False
        else:
            return True

    def keys(self) -> typing.Iterable[typing.Hashable]:
        self.clean()

        return tuple(self._cache.keys())

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {len(tuple(self.keys()))} keys>"


class ConcurrentCachedClient:
    def __init__(self, **client_kwargs):
        self._cache: ExpiringCache = ExpiringCache()
        self._client: typing.Optional[aiohttp.ClientSession] = None
        self._client_kwargs = client_kwargs
        self._pending_requests: dict[tuple, asyncio.Task] = {}

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: typing.Iterable[str] = None,
        headers: dict[str, typing.Any] = None,
        bypass_cache: bool = False,
        cache_for: float,
    ) -> aiohttp.ClientResponse:
        """
        Sends a request with the provided parameters and headers and caches the response
        for `cache_for` seconds. The request is wrapped in a task and will complete even
        if the calling coroutine is cancelled.
        """

        # `aiohttp.ClientSession` should be created with a running event loop
        if self._client is None:
            self._client = aiohttp.ClientSession(**self._client_kwargs)

        final_url = self._client._build_url(url).update_query(params)
        final_headers = self._client._prepare_headers(headers)

        key = (method.upper(), final_url, tuple(final_headers.items()))

        if not bypass_cache and key in self._cache:
            return self._cache[key]

        if key in self._pending_requests:
            return await asyncio.shield(self._pending_requests[key])

        request_task = asyncio.create_task(
            self._client.request(
                method, url, params=params, headers=headers, raise_for_status=True
            )
        )
        request_task.add_done_callback(lambda _: self._pending_requests.pop(key))
        self._pending_requests[key] = request_task

        rsp = await asyncio.shield(self._pending_requests[key])
        self._cache.set(key, rsp, expire_in=cache_for)

        return rsp

    async def get(self, *args, **kwargs) -> aiohttp.ClientResponse:
        return await self.request("GET", *args, **kwargs)

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__}: {len(self._cache.keys())} cached"
            f", {len(self._pending_requests)} pending>"
        )
