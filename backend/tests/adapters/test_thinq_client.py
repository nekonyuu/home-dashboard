"""Client HTTP contre un faux serveur ThinQ local (aucun appel réseau réel)."""

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from app.adapters.outbound.thinq.client import API_KEY, DeviceOffline, ThinQClient
from app.domain.errors import CredentialsRejected, ProviderThrottled, ProviderUnavailable
from tests import thinq_fixture as fx

CLIENT_ID = "11111111-2222-4333-8444-555555555555"


class Fake:
    def __init__(self):
        self.status = 200
        self.error = None
        self.headers = {}
        self.seen = []

    def app(self):
        app = web.Application()
        app.router.add_get("/devices", self.devices)
        app.router.add_get("/devices/{did}/state", self.state)
        return app

    async def _reply(self, request, response):
        self.seen.append(request.headers)
        if self.error is not None or self.status != 200:
            return web.json_response({"error": self.error or {}}, status=self.status, headers=self.headers)
        return web.json_response({"response": response})

    async def devices(self, request):
        return await self._reply(request, fx.devices())

    async def state(self, request):
        return await self._reply(request, fx.state_of(request.match_info["did"]))


@pytest.fixture
async def env():
    fake = Fake()
    server = TestServer(fake.app())
    await server.start_server()
    async with aiohttp.ClientSession() as session:
        client = ThinQClient(session, "secret-pat", "FR", CLIENT_ID, base_url=str(server.make_url("")))
        yield fake, client
    await server.close()


async def test_sends_pat_and_required_headers(env):
    fake, client = env
    assert len(await client.devices()) == 3
    h = fake.seen[0]
    assert h["Authorization"] == "Bearer secret-pat" and h["x-country"] == "FR"
    assert h["x-client-id"] == CLIENT_ID and h["x-api-key"] == API_KEY and h["x-service-phase"] == "OP"
    assert len(h["x-message-id"]) == 22


async def test_state_returns_dict_or_list(env):
    _, client = env
    assert "temperature" in await client.state(fx.device_id_of("DEVICE_REFRIGERATOR"))
    assert isinstance(await client.state(fx.device_id_of("DEVICE_WASHER")), list)


async def test_1222_is_device_offline(env):
    fake, client = env
    fake.status, fake.error = 400, {"code": "1222", "message": "Not connected device"}
    with pytest.raises(DeviceOffline):
        await client.state(fx.device_id_of("DEVICE_WASHER"))


@pytest.mark.parametrize(("status", "code"), [(401, ""), (403, ""), (400, "1103"), (400, "1302")])
async def test_auth_failures_are_credentials_rejected(env, status, code):
    fake, client = env
    fake.status, fake.error = status, {"code": code}
    with pytest.raises(CredentialsRejected) as exc:
        await client.devices()
    assert "secret-pat" not in str(exc.value)


async def test_429_and_quota_code_are_throttled(env):
    fake, client = env
    fake.status, fake.headers = 429, {"Retry-After": "90"}
    with pytest.raises(ProviderThrottled) as exc:
        await client.devices()
    assert exc.value.retry_after == 90
    fake.status, fake.headers, fake.error = 400, {}, {"code": "1306"}
    with pytest.raises(ProviderThrottled) as exc:
        await client.devices()
    assert exc.value.retry_after == 300


async def test_server_error_is_unavailable_without_device_id(env):
    fake, client = env
    fake.status, fake.error = 500, {"code": "2000"}
    did = fx.device_id_of("DEVICE_WASHER")
    with pytest.raises(ProviderUnavailable) as exc:
        await client.state(did)
    assert did not in str(exc.value)


async def test_connection_error_is_unavailable():
    async with aiohttp.ClientSession() as session:
        client = ThinQClient(session, "p", "FR", CLIENT_ID, base_url="http://127.0.0.1:1")
        with pytest.raises(ProviderUnavailable):
            await client.devices()


def test_unknown_region_is_rejected():
    with pytest.raises(ValueError):
        ThinQClient(None, "p", "FR", CLIENT_ID, region="xxx")
