import httpx
import pytest
import respx

from scripts.basecnpj import client as client_module
from scripts.basecnpj.config import Settings
from scripts.basecnpj.errors import AuthError, NotFoundError, RateLimitError, ServerError, ValidationError

BASE_URL = "https://basecnpj.app/api/v1/"


@pytest.fixture(autouse=True)
def no_real_backoff(monkeypatch):
    # evita que os testes de retry esperem os segundos reais do backoff exponencial
    monkeypatch.setattr(client_module, "_retry_wait", lambda retry_state: 0)


@pytest.fixture
def settings():
    return Settings(token="fake-token", base_url=BASE_URL, default_timeout=10.0, heavy_route_timeout=60.0)


@pytest.mark.asyncio
async def test_request_unwraps_success_envelope(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        mock.get("", params={"route": "status"}).respond(
            200, json={"ok": True, "data": {"status": "ok"}}
        )
        data = await client_module.request("status", settings=settings)
    assert data == {"status": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "code", "expected_cls"),
    [
        (400, "invalid_cnpj", ValidationError),
        (401, "unauthorized", AuthError),
        (403, "forbidden", AuthError),
        (404, "not_found", NotFoundError),
    ],
)
async def test_request_maps_non_retryable_errors(settings, status_code, code, expected_cls):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "cnpj", "cnpj": "123"}).respond(
            status_code, json={"ok": False, "error": {"code": code, "message": "erro"}}
        )
        with pytest.raises(expected_cls):
            await client_module.request("cnpj", {"cnpj": "123"}, settings=settings)
    assert route.call_count == 1  # não deve retentar 400/401/403/404


@pytest.mark.asyncio
async def test_request_retries_429_then_succeeds(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "busca", "q": "x"})
        route.side_effect = [
            httpx.Response(429, json={"ok": False, "error": {"code": "rate_limit", "message": "devagar"}}),
            httpx.Response(200, json={"ok": True, "data": {"items": []}}),
        ]
        data = await client_module.request("busca", {"q": "x"}, settings=settings)
    assert data == {"items": []}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_request_exhausts_retries_on_persistent_server_error(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "status"}).respond(
            500, json={"ok": False, "error": {"code": "server_error", "message": "boom"}}
        )
        with pytest.raises(ServerError):
            await client_module.request("status", settings=settings)
    assert route.call_count == 3


@pytest.mark.asyncio
async def test_request_honors_retry_after_header(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "status"})
        route.side_effect = [
            httpx.Response(
                429,
                json={"ok": False, "error": {"code": "rate_limit", "message": "devagar"}},
                headers={"Retry-After": "2"},
            ),
            httpx.Response(200, json={"ok": True, "data": {}}),
        ]
        data = await client_module.request("status", settings=settings)
    assert data == {}
    assert route.call_count == 2


@pytest.mark.asyncio
async def test_request_sends_bearer_token(settings):
    with respx.mock(base_url=BASE_URL) as mock:
        route = mock.get("", params={"route": "status"}).respond(200, json={"ok": True, "data": {}})
        await client_module.request("status", settings=settings)
    sent_auth = route.calls.last.request.headers.get("authorization")
    assert sent_auth == "Bearer fake-token"
