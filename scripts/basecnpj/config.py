from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://basecnpj.app/api/v1/"
DEFAULT_TIMEOUT = 10.0
HEAVY_ROUTE_TIMEOUT = 60.0
HEAVY_ROUTES = frozenset({"avancada", "rede"})


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


_load_dotenv(Path.cwd() / ".env")


@dataclass(frozen=True)
class Settings:
    token: str | None
    base_url: str
    default_timeout: float
    heavy_route_timeout: float

    def timeout_for(self, route: str) -> float:
        return self.heavy_route_timeout if route in HEAVY_ROUTES else self.default_timeout


def get_settings() -> Settings:
    return Settings(
        token=os.environ.get("BASECNPJ_TOKEN"),
        base_url=os.environ.get("BASECNPJ_BASE_URL", DEFAULT_BASE_URL),
        default_timeout=DEFAULT_TIMEOUT,
        heavy_route_timeout=HEAVY_ROUTE_TIMEOUT,
    )
