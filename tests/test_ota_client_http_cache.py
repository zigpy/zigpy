import asyncio
import functools
import pathlib
import socket
import ssl
import unittest.mock

import aiohttp
from aiohttp.abc import AbstractResolver
import pytest

from zigpy.ota.cached_client import ConcurrentCachedClient


# Inspired by https://github.com/aio-libs/aiohttp/blob/master/examples/fake_server.py
class FakeResolver(AbstractResolver):
    _LOCAL_HOST = {0: "127.0.0.1", socket.AF_INET: "127.0.0.1", socket.AF_INET6: "::1"}

    def __init__(self):
        self.ports = {}

    async def resolve(self, host, port=0, family=socket.AF_INET):
        if host not in self.ports:
            raise RuntimeError(f"Domain {host:!r} does not exist")

        return [
            {
                "hostname": host,
                "host": self._LOCAL_HOST[family],
                "port": self.ports[host],
                "family": family,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
        ]

    async def close(self):
        pass


class FakeSite:
    def __init__(self, host, *, resolver, ssl_cert_path) -> None:
        self.resolver = resolver
        self.host = host

        self.app = aiohttp.web.Application()
        self.runner = aiohttp.web.AppRunner(self.app)

        if ssl_cert_path is not None:
            ssl_cert = pathlib.Path(__file__).parent / "server.crt"
            ssl_key = pathlib.Path(__file__).parent / "server.key"

            self.ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            self.ssl_context.load_cert_chain(str(ssl_cert), str(ssl_key))
        else:
            self.ssl_context = None

    async def start(self):
        port = aiohttp.test_utils.unused_port()
        self.resolver.ports[self.host] = port

        await self.runner.setup()

        site = aiohttp.web.TCPSite(
            self.runner, "127.0.0.1", port, ssl_context=self.ssl_context
        )
        await site.start()

    async def stop(self) -> None:
        await self.runner.cleanup()


@pytest.fixture
async def fake_server(loop, tmp_path):
    resolver = FakeResolver()
    connector = aiohttp.TCPConnector(resolver=resolver, ssl=False)

    patched_init = functools.partialmethod(
        aiohttp.ClientSession.__init__, connector=connector
    )

    # aiohttp relies on the event loop being present at object construction time
    async def register(*hosts):
        return [
            FakeSite(host, resolver=resolver, ssl_cert_path=tmp_path) for host in hosts
        ]

    with unittest.mock.patch.object(aiohttp.ClientSession, "__init__", patched_init):
        yield register


@pytest.fixture
async def test_server(fake_server):
    (server,) = await fake_server("example.org")
    routes = aiohttp.web.RouteTableDef()

    counter = 0
    delay_futures = {}

    @routes.get("/test")
    async def test_handler(request):
        nonlocal counter
        counter += 1

        return aiohttp.web.json_response({"counter": counter})

    @routes.get("/wait_for/{start_id}")
    async def wait_for_handler(request):
        start_id = request.match_info["start_id"]

        if start_id not in delay_futures or delay_futures[start_id].done():
            delay_futures[start_id] = asyncio.get_running_loop().create_future()

        await asyncio.shield(delay_futures[start_id])

        nonlocal counter
        counter += 1

        return aiohttp.web.json_response({"counter": counter})

    @routes.get("/start/{start_id}")
    async def start_handler(request):
        start_id = request.match_info["start_id"]

        delay_futures[start_id].set_result(True)

        return aiohttp.web.json_response({})

    server.app.router.add_routes(routes)
    await server.start()

    yield server


async def test_concurrent_get(test_server):
    client = ConcurrentCachedClient()
    responses = []

    for i in range(10):
        rsp = await client.get(
            url="https://example.org/test",
            params={"p1": "foo", "p2": "bar"},
            headers={"Custom": "test"},
            cache_for=30,
        )
        responses.append(await rsp.json())

    assert responses == [{"counter": 1} for _ in range(10)]


async def test_request_hashing(test_server):
    client = ConcurrentCachedClient()
    responses = []

    async def send_req(url, params={}, headers={}):
        rsp = await client.get(url=url, params=params, headers=headers, cache_for=30)
        responses.append(await rsp.json())

    # URL params are hashed based on the final constructed URL
    for i in range(5):
        await send_req("https://example.org/test", {"p1": "foo", "p2": "bar"})

    for i in range(3):
        await send_req("https://example.org/test?p1=foo", {"p2": "bar"})

    for i in range(2):
        await send_req("https://example.org/test?p1=foo&p2=bar", {})

    assert responses == [{"counter": 1} for _ in range(10)]

    # Changing a single param generates a new hash
    responses = []

    for i in range(5):
        await send_req("https://example.org/test", {"p1": "foo", "p2": "baz"})

    for i in range(3):
        await send_req("https://example.org/test?p1=foo", {"p2": "baz"})

    for i in range(2):
        await send_req("https://example.org/test?p1=foo&p2=baz", {})

    assert responses == [{"counter": 2} for _ in range(10)]

    # So does changing a header
    responses = []
    headers = {"Custom": "1"}

    for i in range(5):
        await send_req("https://example.org/test", {"p1": "foo", "p2": "baz"}, headers)

    for i in range(3):
        await send_req("https://example.org/test?p1=foo", {"p2": "baz"}, headers)

    for i in range(2):
        await send_req("https://example.org/test?p1=foo&p2=baz", {}, headers)

    assert responses == [{"counter": 3} for _ in range(10)]


async def test_request_task_cancellation(test_server):
    client = ConcurrentCachedClient()

    # Send 10 "delayed" GET requests
    reqs = [
        asyncio.create_task(
            client.get(url="https://example.org/wait_for/1", cache_for=30)
        )
        for i in range(10)
    ]

    await asyncio.sleep(0.1)

    # Cancel the first 5
    for r in reqs[:5]:
        r.cancel()

    await asyncio.sleep(0.1)

    # Then allow the server to send back a response
    await client.get(url="https://example.org/start/1", cache_for=0)

    responses = [await (await r).json() for r in reqs[5:]]

    # Despite the original request being cancelled, the launched request will still
    # complete and the remaining 5 concurrent requests will succeed
    assert responses == [{"counter": 1} for _ in range(5)]
