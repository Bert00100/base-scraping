from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import httpx

from scripts.basecnpj import routes
from scripts.basecnpj.config import Settings
from scripts.basecnpj.models import CNPJDetalhe

from .icp import ICP

SEIS_MESES_DIAS = 182


@dataclass
class ValidacaoResult:
    cnpj: str
    status: str  # "validado" | "descartado"
    detalhe: CNPJDetalhe | None = None
    discard_reason: str | None = None
    flags: list[str] = field(default_factory=list)
    cnae_match: str | None = None  # "principal" | "secundario" | None


def _parse_data(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


async def validate_lead(
    cnpj: str,
    icp: ICP,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    hoje: date | None = None,
    raw: dict[str, Any] | None = None,
) -> ValidacaoResult:
    """S3 — hidrata via `route=cnpj` (a menos que `raw` já venha pronto, útil pra
    testar sem rede) e aplica as regras de descarte/flag da seção 5 do
    ARCTETURE.md, na ordem descrita lá. Primeira regra que descarta já retorna.
    """
    if raw is None:
        raw = await routes.cnpj(cnpj, settings=settings, client=client)
    detalhe = CNPJDetalhe.model_validate(raw)
    matriz = detalhe.estabelecimento_matriz

    situacao = matriz.situacao_cadastral if matriz else None
    if situacao is not None and icp.situacao is not None and situacao != icp.situacao:
        return ValidacaoResult(
            cnpj=cnpj,
            status="descartado",
            detalhe=detalhe,
            discard_reason=f"situacao_cadastral={situacao} (esperado {icp.situacao})",
        )

    cnae_match: str | None = None
    if icp.cnaes:
        principal = detalhe.cnae_principal()
        secundarios = detalhe.cnaes_secundarios()
        if principal in icp.cnaes:
            cnae_match = "principal"
        elif any(c in icp.cnaes for c in secundarios):
            cnae_match = "secundario"
        else:
            return ValidacaoResult(
                cnpj=cnpj,
                status="descartado",
                detalhe=detalhe,
                discard_reason="cnae fora do ICP (nem principal nem secundário bate)",
            )

    if icp.porte is not None and detalhe.porte_codigo is not None and detalhe.porte_codigo != icp.porte:
        return ValidacaoResult(
            cnpj=cnpj,
            status="descartado",
            detalhe=detalhe,
            discard_reason=f"porte={detalhe.porte_codigo} (esperado {icp.porte})",
        )

    quer_matriz = icp.filtros_extra.get("matriz_filial") == "1"
    if quer_matriz:
        matriz_filial_codigo = detalhe.matriz_filial_codigo()
        if matriz_filial_codigo is not None and matriz_filial_codigo != "1":
            return ValidacaoResult(
                cnpj=cnpj,
                status="descartado",
                detalhe=detalhe,
                discard_reason="é filial e o ICP pede matriz",
            )

    flags: list[str] = []
    data_abertura = _parse_data(matriz.data_inicio_atividade if matriz else None)
    if data_abertura is not None:
        referencia = hoje if hoje is not None else date.today()
        if (referencia - data_abertura).days < SEIS_MESES_DIAS:
            flags.append("empresa_nova")

    if cnae_match == "secundario":
        flags.append("cnae_secundario")

    tem_contato_cadastral = bool((matriz.email if matriz else None) or detalhe.telefones)
    if tem_contato_cadastral:
        flags.append("contato_cadastral_disponivel")

    return ValidacaoResult(cnpj=cnpj, status="validado", detalhe=detalhe, flags=flags, cnae_match=cnae_match)
