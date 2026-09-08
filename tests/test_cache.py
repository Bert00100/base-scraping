import pytest

from scripts.basecnpj import cache as cache_module


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "basecnpj-cache"


@pytest.mark.asyncio
async def test_get_or_fetch_hits_cache_on_second_identical_call(cache_dir):
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return {"razao_social": "EMPRESA TESTE"}

    params = {"cnpj": "00000000000191"}
    first = await cache_module.get_or_fetch("cnpj", params, fetch, cache_dir=cache_dir, now=1_000_000)
    second = await cache_module.get_or_fetch("cnpj", params, fetch, cache_dir=cache_dir, now=1_000_100)

    assert first == second == {"razao_social": "EMPRESA TESTE"}
    assert calls == 1


@pytest.mark.asyncio
async def test_get_or_fetch_refetches_after_ttl_expires(cache_dir):
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return {"call": calls}

    params = {"cnpj": "00000000000191"}
    ttl = 60.0
    first = await cache_module.get_or_fetch(
        "cnpj", params, fetch, cache_dir=cache_dir, ttl=ttl, now=0
    )
    second = await cache_module.get_or_fetch(
        "cnpj", params, fetch, cache_dir=cache_dir, ttl=ttl, now=ttl + 1
    )

    assert first == {"call": 1}
    assert second == {"call": 2}
    assert calls == 2


@pytest.mark.asyncio
async def test_status_route_is_never_cached(cache_dir):
    calls = 0

    async def fetch():
        nonlocal calls
        calls += 1
        return {"status": "ok"}

    await cache_module.get_or_fetch("status", {}, fetch, cache_dir=cache_dir, now=0)
    await cache_module.get_or_fetch("status", {}, fetch, cache_dir=cache_dir, now=0)

    assert calls == 2


def test_different_params_use_different_cache_entries(cache_dir):
    cache_module.write_cache("cnpj", {"cnpj": "111"}, {"a": 1}, cache_dir=cache_dir, now=0)
    cache_module.write_cache("cnpj", {"cnpj": "222"}, {"a": 2}, cache_dir=cache_dir, now=0)

    assert cache_module.read_cache("cnpj", {"cnpj": "111"}, cache_dir=cache_dir, now=0) == {"a": 1}
    assert cache_module.read_cache("cnpj", {"cnpj": "222"}, cache_dir=cache_dir, now=0) == {"a": 2}
