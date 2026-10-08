from __future__ import annotations

from typing import Any

import httpx

from . import cache as cache_module
from . import client as client_module
from scripts.utils import only_digits

from .config import Settings, get_settings


async def _cached_request(
    route: str,
    params: dict[str, Any],
    *,
    settings: Settings | None,
    client: httpx.AsyncClient | None,
    use_cache: bool,
) -> dict[str, Any]:
    settings = settings or get_settings()

    async def fetch() -> dict[str, Any]:
        return await client_module.request(route, params, settings=settings, client=client)

    if not use_cache:
        return await fetch()
    return await cache_module.get_or_fetch(route, params, fetch)


async def status(
    *, settings: Settings | None = None, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    """route=status — preflight público, nunca cacheado."""
    return await client_module.request("status", {}, settings=settings, client=client)


async def busca(
    q: str,
    page: int = 1,
    per_page: int = 15,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """route=busca — busca textual (S2, resolução de identidade)."""
    params = {"q": q, "page": page, "per_page": per_page}
    return await _cached_request("busca", params, settings=settings, client=client, use_cache=use_cache)


async def cnpj(
    cnpj: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """route=cnpj — detalhe completo (S3, validação e hidratação cadastral)."""
    params = {"cnpj": only_digits(cnpj)}
    return await _cached_request("cnpj", params, settings=settings, client=client, use_cache=use_cache)


async def sugestao(
    q: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """route=sugestao — autocomplete (S2, candidatos rápidos)."""
    params = {"q": q}
    return await _cached_request("sugestao", params, settings=settings, client=client, use_cache=use_cache)


async def avancada(
    *,
    uf: str | None = None,
    municipio: str | None = None,
    cnae: str | None = None,
    porte: str | None = None,
    situacao: str | None = None,
    capital_min: float | None = None,
    capital_max: float | None = None,
    socio: str | None = None,
    cep: str | None = None,
    matriz_filial: str | None = None,
    page: int = 1,
    per_page: int = 15,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """route=avancada — motor primário de descoberta (S1).

    Nomes de parâmetro confirmados empiricamente contra a API real (o ARCTETURE.md
    só documentava os conceitos, não os nomes de query string — ver
    references/basecnpj.md, seção "Parâmetros confirmados da busca avançada"):
    `situacao` e `porte` usam os códigos numéricos do cadastro (ex. situacao="02"
    é Ativa, porte="01" é Micro empresa), não os rótulos por extenso.
    """
    raw_params = {
        "uf": uf,
        "municipio": municipio,
        "cnae": cnae,
        "porte": porte,
        "situacao": situacao,
        "capital_min": capital_min,
        "capital_max": capital_max,
        "socio": socio,
        "cep": cep,
        "matriz_filial": matriz_filial,
        "page": page,
        "per_page": per_page,
    }
    params = {k: v for k, v in raw_params.items() if v is not None}
    return await _cached_request("avancada", params, settings=settings, client=client, use_cache=use_cache)


async def rede(
    cnpj: str,
    depth: int = 2,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """route=rede — grafo societário, exclusivo Business (S5, expansão)."""
    params = {"cnpj": only_digits(cnpj), "depth": depth}
    return await _cached_request("rede", params, settings=settings, client=client, use_cache=use_cache)
