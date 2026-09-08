from __future__ import annotations

from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import Settings, get_settings
from .errors import BaseCNPJError, RateLimitError, ServerError, map_error

_DEFAULT_BACKOFF = wait_exponential(multiplier=1, min=1, max=20)


def _retry_wait(retry_state):
    exc = retry_state.outcome.exception()
    if isinstance(exc, RateLimitError) and exc.retry_after:
        return exc.retry_after
    return _DEFAULT_BACKOFF(retry_state)


def _unwrap(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise BaseCNPJError(
            response.status_code, "invalid_json", "Resposta não é JSON válido"
        ) from exc

    if payload.get("ok"):
        return payload.get("data", {})

    error = payload.get("error", {})
    retry_after = None
    if response.status_code == 429:
        header = response.headers.get("Retry-After")
        if header:
            try:
                retry_after = float(header)
            except ValueError:
                retry_after = None

    raise map_error(
        response.status_code,
        error.get("code", "unknown"),
        error.get("message", ""),
        retry_after=retry_after,
    )


async def request(
    route: str,
    params: dict[str, Any] | None = None,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Chama uma rota do BaseCNPJ e devolve o `data` já desempacotado do envelope {ok, data}.

    Erros de rede/HTTP viram exceções de `errors.py`. 429/500 são retentados (backoff
    exponencial, honrando Retry-After em 429) até 3 tentativas; os demais códigos
    (400/403/404/405) propagam na primeira tentativa, sem retry.
    """
    settings = settings or get_settings()
    query = {"route": route, **(params or {})}
    headers = {}
    if settings.token:
        headers["Authorization"] = f"Bearer {settings.token}"

    timeout = settings.timeout_for(route)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=settings.base_url)

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type((RateLimitError, ServerError)),
            stop=stop_after_attempt(3),
            wait=_retry_wait,
            reraise=True,
        ):
            with attempt:
                response = await http_client.get("", params=query, headers=headers, timeout=timeout)
                return _unwrap(response)
    finally:
        if owns_client:
            await http_client.aclose()
