from __future__ import annotations

import re
from dataclasses import dataclass

from scripts.utils import only_digits


_TRECHO_NUMERICO_RE = re.compile(r"\d[\d\s().\-/]*\d")
TELEFONE_COM_DDD_MIN_DIGITOS = 10


def _trechos_numericos(html: str) -> list[str]:
    """Trechos da página que parecem um número (dígitos com separadores), já
    normalizados para só dígitos — números soltos em tags diferentes não se juntam.
    """
    return [only_digits(trecho) for trecho in _TRECHO_NUMERICO_RE.findall(html)]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


@dataclass
class MatchResult:
    matched: bool
    sinais: list[str]  # quais sinais bateram: "cnpj", "razao_social", "nome_fantasia", "telefone"


def validar_match(
    html: str,
    *,
    cnpj: str,
    razao_social: str | None = None,
    nome_fantasia: str | None = None,
    telefone: str | None = None,
) -> MatchResult:
    """4.1 do ARCTETURE.md — o site precisa mencionar o CNPJ, a razão social, o
    nome fantasia ou o telefone. Sem nenhum desses sinais, é match fraco: não
    confirma o site (quem chama descarta em vez de gravar lixo).
    """
    texto = _normalize_text(html)
    trechos = _trechos_numericos(html)
    sinais: list[str] = []

    cnpj_digitos = only_digits(cnpj)
    if cnpj_digitos and any(cnpj_digitos in trecho for trecho in trechos):
        sinais.append("cnpj")

    if razao_social and _normalize_text(razao_social) in texto:
        sinais.append("razao_social")

    if nome_fantasia and _normalize_text(nome_fantasia) in texto:
        sinais.append("nome_fantasia")

    if telefone:
        telefone_digitos = only_digits(telefone)
        if telefone_digitos:
            if len(telefone_digitos) < TELEFONE_COM_DDD_MIN_DIGITOS:
                # sem DDD: o trecho precisa terminar no número, não só conter
                bateu = any(trecho.endswith(telefone_digitos) for trecho in trechos)
            else:
                bateu = any(telefone_digitos in trecho for trecho in trechos)
            if bateu:
                sinais.append("telefone")

    return MatchResult(matched=bool(sinais), sinais=sinais)

