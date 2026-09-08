from __future__ import annotations

import re
from dataclasses import dataclass, field

from selectolax.parser import HTMLParser

ECOMMERCE_SIGNALS = [
    "adicionar ao carrinho",
    "meu carrinho",
    "finalizar compra",
    "checkout",
    "frete grátis",
    "cupom de desconto",
    "comprar agora",
]

TECH_FINGERPRINTS: dict[str, list[str]] = {
    "wordpress": [r"wp-content", r"wp-includes", r'name="generator" content="wordpress'],
    "shopify": [r"cdn\.shopify\.com", r"shopify"],
    "vtex": [r"vteximg\.com\.br", r"vtex"],
    "woocommerce": [r"woocommerce"],
    "wix": [r"wix\.com", r"wixstatic"],
    "squarespace": [r"squarespace"],
}

# Heurística grosseira — não é contagem confiável de funcionários, só um sinal
# relativo de que a página "fala de gente" (cargos de liderança citados).
TEAM_TITLE_KEYWORDS = [
    "diretor",
    "diretora",
    "gerente",
    "sócio",
    "sócia",
    "ceo",
    "founder",
    "fundador",
    "fundadora",
    "coordenador",
    "coordenadora",
]

_SPA_MARKERS = ['id="root"', 'id="__next"', "you need to enable javascript", "please enable javascript"]
_SPA_MIN_TEXT_LEN = 200


@dataclass
class ContextSignals:
    ecommerce: bool = False
    tecnologias: list[str] = field(default_factory=list)
    indicios_equipe: int = 0


def detect_context_signals(html: str) -> ContextSignals:
    """4.4 do ARCTETURE.md — sinais determinísticos de contexto. `indicios_equipe`
    é uma heurística de contagem de menções a cargos, não um número confiável de
    funcionários; serve só como sinal relativo para o score (S6).
    """
    texto = HTMLParser(html).text(separator=" ").lower()
    html_lower = html.lower()

    ecommerce = any(sinal in texto for sinal in ECOMMERCE_SIGNALS)
    tecnologias = [
        nome
        for nome, padroes in TECH_FINGERPRINTS.items()
        if any(re.search(padrao, html_lower) for padrao in padroes)
    ]
    indicios_equipe = sum(texto.count(kw) for kw in TEAM_TITLE_KEYWORDS)

    return ContextSignals(ecommerce=ecommerce, tecnologias=tecnologias, indicios_equipe=indicios_equipe)


def parece_requer_js(html: str) -> bool:
    """Heurística para sites que renderizam via JS no cliente (SPA vazia no HTML
    estático): marcador comum de framework SPA + pouquíssimo texto. Playwright
    fica fora do v1 (decisão fechada, seção 11) — esses sites são só marcados,
    não processados.
    """
    texto = HTMLParser(html).text(separator=" ").strip()
    html_lower = html.lower()
    tem_marcador = any(marcador in html_lower for marcador in _SPA_MARKERS)
    pouco_texto = len(texto) < _SPA_MIN_TEXT_LEN
    return tem_marcador and pouco_texto
