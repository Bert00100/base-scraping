from __future__ import annotations

from dataclasses import dataclass

from scripts.pipeline.validate import ValidacaoResult
from scripts.scraping.enrich import EnrichmentResult

# Pesos da seção 8 do ARCTETURE.md — somam 100.
PESO_ADERENCIA_ICP = 30
PESO_QUALIDADE_CONTATO = 30
PESO_PRESENCA_DIGITAL = 20
PESO_SAUDE_CADASTRAL = 20

_EMAIL_NIVEL_PONTOS = {
    "maxima": 22,
    "alta_nominal": 20,
    "alta": 16,
    "boa": 10,
    "media": 5,
    "baixa": 2,
    "invalido": 0,
}


@dataclass
class ScoreBreakdown:
    aderencia_icp: float
    qualidade_contato: float
    presenca_digital: float
    saude_cadastral: float

    @property
    def total(self) -> float:
        return self.aderencia_icp + self.qualidade_contato + self.presenca_digital + self.saude_cadastral

    def as_dict(self) -> dict[str, float]:
        return {
            "aderencia_icp": self.aderencia_icp,
            "qualidade_contato": self.qualidade_contato,
            "presenca_digital": self.presenca_digital,
            "saude_cadastral": self.saude_cadastral,
            "total": self.total,
        }


def _score_aderencia_icp(validacao: ValidacaoResult) -> float:
    """CNAE principal vale o peso cheio; só como secundário rebaixa (seção 3.3 e
    S3 do ARCTETURE.md dizem "mantém, rebaixa score" — nunca zera)."""
    if validacao.cnae_match == "principal":
        return float(PESO_ADERENCIA_ICP)
    if validacao.cnae_match == "secundario":
        return round(PESO_ADERENCIA_ICP * 0.6, 2)
    return float(PESO_ADERENCIA_ICP)  # ICP sem filtro de CNAE — nada a penalizar aqui


def _score_qualidade_contato(validacao: ValidacaoResult, enrichment: EnrichmentResult | None) -> float:
    pontos_email = 0.0
    if enrichment and enrichment.emails:
        pontos_email = max(_EMAIL_NIVEL_PONTOS.get(e.confianca, 0) for e in enrichment.emails)

    pontos_telefone_whatsapp = 0.0
    if enrichment:
        if enrichment.telefones:
            pontos_telefone_whatsapp += 4
        if enrichment.whatsapp:
            pontos_telefone_whatsapp += 4

    # sem nenhum e-mail vindo do scraping, o contato cadastral (S3) ainda conta —
    # "ganho direto: contato antes de qualquer scraping" (seção 5 do ARCTETURE.md)
    pontos_cadastral_bonus = 0.0
    if pontos_email == 0 and "contato_cadastral_disponivel" in validacao.flags:
        pontos_cadastral_bonus = 8.0

    total = pontos_email + pontos_telefone_whatsapp + pontos_cadastral_bonus
    return min(float(PESO_QUALIDADE_CONTATO), total)


def _score_presenca_digital(enrichment: EnrichmentResult | None) -> float:
    if enrichment is None or not enrichment.site_matched:
        return 0.0
    pontos = 12.0
    if enrichment.redes_sociais:
        pontos += min(6.0, 2.0 * len(enrichment.redes_sociais))
    if enrichment.context and (enrichment.context.ecommerce or enrichment.context.tecnologias):
        pontos += 2.0
    return min(float(PESO_PRESENCA_DIGITAL), pontos)


def _score_saude_cadastral(validacao: ValidacaoResult) -> float:
    # "situação ativa" já é pré-requisito pra um lead chegar como validado (S3) —
    # o pontos-base aqui reflete isso; o resto diferencia maturidade/capital.
    pontos = 10.0
    if "empresa_nova" not in validacao.flags:
        pontos += 5.0
    detalhe = validacao.detalhe
    capital = getattr(detalhe, "capital_social", None) if detalhe else None
    if capital and capital > 0:
        pontos += 5.0
    return min(float(PESO_SAUDE_CADASTRAL), pontos)


def compute_score(validacao: ValidacaoResult, enrichment: EnrichmentResult | None = None) -> ScoreBreakdown:
    """S6 — pesos da seção 8 do ARCTETURE.md: 30 aderência ao ICP, 30 qualidade de
    contato, 20 presença digital, 20 saúde cadastral. `enrichment` pode ser None
    (lead sem scraping bem-sucedido continua pontuável, só com menos campos —
    premissa central do ARCTETURE.md).
    """
    return ScoreBreakdown(
        aderencia_icp=_score_aderencia_icp(validacao),
        qualidade_contato=_score_qualidade_contato(validacao, enrichment),
        presenca_digital=_score_presenca_digital(enrichment),
        saude_cadastral=_score_saude_cadastral(validacao),
    )
