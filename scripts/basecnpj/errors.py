from __future__ import annotations


class BaseCNPJError(Exception):
    """Erro base para qualquer falha ao chamar a API do BaseCNPJ."""

    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(f"[{status_code} {code}] {message}")


class ValidationError(BaseCNPJError):
    """400 — erro de programação nosso (missing_q, invalid_cnpj, no_filters). Não repetir."""


class AuthError(BaseCNPJError):
    """403 — token inválido/expirado ou plano não permite a rota. Abortar execução."""


class NotFoundError(BaseCNPJError):
    """404 — CNPJ/rota inexistente. Marcar lead como não resolvido e seguir."""


class MethodNotAllowedError(BaseCNPJError):
    """405 — nunca deveria acontecer (só usamos GET)."""


class RateLimitError(BaseCNPJError):
    """429 — respeitar Retry-After e fazer backoff exponencial."""

    def __init__(self, status_code: int, code: str, message: str, retry_after: float | None = None):
        super().__init__(status_code, code, message)
        self.retry_after = retry_after


class ServerError(BaseCNPJError):
    """500 — retry com backoff, até 3 tentativas, depois enfileirar."""


_STATUS_TO_EXCEPTION: dict[int, type[BaseCNPJError]] = {
    400: ValidationError,
    403: AuthError,
    404: NotFoundError,
    405: MethodNotAllowedError,
    429: RateLimitError,
    500: ServerError,
}


def map_error(
    status_code: int,
    code: str = "unknown",
    message: str = "",
    retry_after: float | None = None,
) -> BaseCNPJError:
    """Mapeia um status HTTP (e o código do envelope de erro) para a exceção certa.

    Códigos/HTTP não catalogados na tabela de erros caem no BaseCNPJError genérico,
    em vez de propagar um KeyError.
    """
    exc_class = _STATUS_TO_EXCEPTION.get(status_code, BaseCNPJError)
    if exc_class is RateLimitError:
        return RateLimitError(status_code, code, message, retry_after=retry_after)
    return exc_class(status_code, code, message)
