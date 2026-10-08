import pytest

from scripts.basecnpj.errors import (
    AuthError,
    BaseCNPJError,
    MethodNotAllowedError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
    map_error,
)


@pytest.mark.parametrize(
    ("status_code", "code", "expected_cls"),
    [
        (400, "missing_q", ValidationError),
        (400, "invalid_cnpj", ValidationError),
        (400, "no_filters", ValidationError),
        (401, "unauthorized", AuthError),
        (403, "forbidden", AuthError),
        (403, "plan_required", AuthError),
        (404, "not_found", NotFoundError),
        (404, "unknown_route", NotFoundError),
        (405, "method_not_allowed", MethodNotAllowedError),
        (429, "rate_limit", RateLimitError),
        (500, "server_error", ServerError),
    ],
)
def test_map_error_known_codes(status_code, code, expected_cls):
    exc = map_error(status_code, code, "mensagem qualquer")
    assert isinstance(exc, expected_cls)
    assert exc.status_code == status_code
    assert exc.code == code


def test_map_error_unknown_status_falls_back_to_base_exception():
    exc = map_error(418, "teapot", "sou um bule")
    assert type(exc) is BaseCNPJError
    assert exc.status_code == 418


def test_rate_limit_error_carries_retry_after():
    exc = map_error(429, "rate_limit", "devagar", retry_after=12.5)
    assert isinstance(exc, RateLimitError)
    assert exc.retry_after == 12.5
