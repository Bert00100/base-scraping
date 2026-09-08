from scripts.pipeline.score import compute_score
from scripts.pipeline.validate import ValidacaoResult
from scripts.scraping.context_signals import ContextSignals
from scripts.scraping.email_verify import EmailVerification
from scripts.scraping.enrich import EnrichmentResult


class _FakeDetalhe:
    def __init__(self, capital_social):
        self.capital_social = capital_social


def test_lead_perfeito_pontua_perto_do_maximo():
    validacao = ValidacaoResult(
        cnpj="1",
        status="validado",
        cnae_match="principal",
        flags=["contato_cadastral_disponivel"],
        detalhe=_FakeDetalhe(capital_social=50000),
    )
    enrichment = EnrichmentResult(
        site="https://empresa.com.br/",
        site_matched=True,
        emails=[EmailVerification(email="dono@empresa.com.br", nivel=5, cruzamento_cadastral=True, motivos=[])],
        telefones=["1130001111"],
        whatsapp=["5511999998888"],
        redes_sociais={"instagram": "x", "facebook": "y", "linkedin": "z"},
        context=ContextSignals(ecommerce=False, tecnologias=["wordpress"], indicios_equipe=1),
    )

    breakdown = compute_score(validacao, enrichment)

    assert breakdown.aderencia_icp == 30
    assert breakdown.qualidade_contato == 30  # capado no peso máximo
    assert breakdown.presenca_digital == 20  # capado no peso máximo
    assert breakdown.saude_cadastral == 20
    assert breakdown.total == 100


def test_lead_fraco_pontua_baixo():
    validacao = ValidacaoResult(
        cnpj="2",
        status="validado",
        cnae_match="secundario",
        flags=["empresa_nova"],
        detalhe=_FakeDetalhe(capital_social=0),
    )

    breakdown = compute_score(validacao, enrichment=None)

    assert breakdown.aderencia_icp == 18  # 60% de 30, rebaixado por ser CNAE secundário
    assert breakdown.qualidade_contato == 0
    assert breakdown.presenca_digital == 0
    assert breakdown.saude_cadastral == 10  # só o piso de situação ativa
    assert breakdown.total == 28


def test_lead_sem_scraping_mas_com_contato_cadastral_nao_zera_qualidade_contato():
    validacao = ValidacaoResult(
        cnpj="3",
        status="validado",
        cnae_match="principal",
        flags=["contato_cadastral_disponivel"],
    )

    breakdown = compute_score(validacao, enrichment=None)

    assert breakdown.qualidade_contato == 8
    assert breakdown.presenca_digital == 0


def test_score_breakdown_as_dict_includes_total():
    validacao = ValidacaoResult(cnpj="4", status="validado", cnae_match="principal", flags=[])
    breakdown = compute_score(validacao, enrichment=None)
    d = breakdown.as_dict()
    assert d["total"] == breakdown.total
    assert set(d.keys()) == {"aderencia_icp", "qualidade_contato", "presenca_digital", "saude_cadastral", "total"}


def test_qualidade_contato_soma_email_telefone_whatsapp_ate_o_teto():
    validacao = ValidacaoResult(cnpj="5", status="validado", cnae_match="principal", flags=[])
    enrichment = EnrichmentResult(
        site="https://x.com.br",
        site_matched=True,
        emails=[EmailVerification(email="a@x.com.br", nivel=3, motivos=[])],  # "boa" = 10 pontos
        telefones=["1111111111"],
        whatsapp=["5511999998888"],
    )
    breakdown = compute_score(validacao, enrichment)
    # 10 (email "boa") + 4 (telefone) + 4 (whatsapp) = 18
    assert breakdown.qualidade_contato == 18
