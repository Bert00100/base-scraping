from __future__ import annotations

import asyncio
import json
from typing import Any

import typer

from scripts.basecnpj import routes

app = typer.Typer(help="Cliente de teste manual para as rotas do BaseCNPJ (não é o pipeline final).")


def _print(data: Any) -> None:
    typer.echo(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _run(coro):
    return asyncio.run(coro)


@app.command()
def status() -> None:
    """route=status — preflight público."""
    _print(_run(routes.status()))


@app.command()
def busca(q: str, page: int = 1, per_page: int = 15) -> None:
    """route=busca — busca textual (S2)."""
    _print(_run(routes.busca(q, page=page, per_page=per_page)))


@app.command()
def cnpj(cnpj: str) -> None:
    """route=cnpj — detalhe completo (S3)."""
    _print(_run(routes.cnpj(cnpj)))


@app.command()
def sugestao(q: str) -> None:
    """route=sugestao — autocomplete (S2)."""
    _print(_run(routes.sugestao(q)))


@app.command()
def avancada(
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
) -> None:
    """route=avancada — motor primário de descoberta (S1).

    Nomes de filtro confirmados em references/basecnpj.md: `situacao` e `porte`
    usam código numérico do cadastro (ex. situacao=02 é Ativa), não o rótulo.
    """
    _print(
        _run(
            routes.avancada(
                uf=uf,
                municipio=municipio,
                cnae=cnae,
                porte=porte,
                situacao=situacao,
                capital_min=capital_min,
                capital_max=capital_max,
                socio=socio,
                cep=cep,
                matriz_filial=matriz_filial,
                page=page,
                per_page=per_page,
            )
        )
    )


@app.command()
def rede(cnpj: str, depth: int = 2) -> None:
    """route=rede — grafo societário, exclusivo Business (S5)."""
    _print(_run(routes.rede(cnpj, depth=depth)))


if __name__ == "__main__":
    app()
