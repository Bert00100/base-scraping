from scripts.basecnpj.models import CNPJDetalhe
from scripts.pipeline.export import build_lead_json, export_leads
from scripts.pipeline.score import ScoreBreakdown
from scripts.pipeline.validate import ValidacaoResult
from scripts.scraping.email_verify import EmailVerification
from scripts.scraping.enrich import EnrichmentResult

_RAW_DETALHE = {
    "cnpj_basico": "43292842",
    "cnpj_completo_formatado": "43.292.842/0001-77",
    "razao_social": "EMPRESA TESTE LTDA",
    "capital_social": 15000,
    "porte_descricao": "Micro empresa",
    "natureza_juridica_descricao": "Sociedade Empresária Limitada",
    "estabelecimento_matriz": {
        "nome_fantasia": "TESTE ODONTO",
        "situacao_descricao": "Ativa",
        "data_inicio_atividade": "2020-01-01",
        "email": "contato@empresa.com.br",
        "logradouro": "RUA TESTE 123",
        "municipio": "HOLAMBRA",
        "uf": "SP",
        "cep": "13825-000",
    },
    "estabelecimentos": [{"cnpj_completo_formatado": "43.292.842/0001-77", "matriz_filial_codigo": "1"}],
    "cnaes": [{"tipo": "Principal", "cnae": "8630504", "desc": "Odontologia"}],
    "telefones": [{"tipo": "comercial", "ddd": "11", "numero": "34357093"}],
    "socios": [{"nome_razao": "FULANO DE TAL", "qualificacao_descricao": "Sócio-Administrador"}],
}

_BREAKDOWN = ScoreBreakdown(aderencia_icp=30, qualidade_contato=20, presenca_digital=12, saude_cadastral=20)


def _validacao(**overrides):
    defaults = dict(
        cnpj="43292842000177",
        status="validado",
        detalhe=CNPJDetalhe.model_validate(_RAW_DETALHE),
        flags=["contato_cadastral_disponivel"],
        cnae_match="principal",
    )
    defaults.update(overrides)
    return ValidacaoResult(**defaults)


def test_build_lead_json_includes_cadastral_fields_and_proveniencia():
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=None, validado_em=1000.0)

    assert lead["cnpj"] == "43292842000177"
    assert lead["razao_social"] == "EMPRESA TESTE LTDA"
    assert lead["nome_fantasia"] == "TESTE ODONTO"
    assert lead["cnae_principal"] == "8630504"
    assert lead["situacao_cadastral"] == "Ativa"
    assert lead["endereco"] == {"logradouro": "RUA TESTE 123", "municipio": "HOLAMBRA", "uf": "SP", "cep": "13825-000"}
    assert lead["telefone_cadastral"] == "(11) 34357093"
    assert lead["matriz_filial"] == "matriz"
    assert lead["socios"][0]["nome_razao"] == "FULANO DE TAL"
    assert lead["score"] == 82

    for campo in ("razao_social", "cnae_principal", "situacao_cadastral", "score"):
        assert campo in lead["proveniencia"], campo
        assert lead["proveniencia"][campo]["timestamp"] == 1000.0 or campo == "score"

    assert lead["proveniencia"]["cnpj"]["fonte"] == "basecnpj"
    assert lead["proveniencia"]["cnpj"]["rota_ou_url"] == "route=cnpj"


def test_build_lead_json_without_detalhe_only_has_cnpj_and_score():
    validacao = ValidacaoResult(cnpj="123", status="validado", cnae_match=None, flags=[])
    lead = build_lead_json(validacao, _BREAKDOWN, enrichment=None)

    assert lead["cnpj"] == "123"
    assert "razao_social" not in lead
    assert "score" in lead
    assert "razao_social" not in lead["proveniencia"]


def test_build_lead_json_without_enrichment_has_no_scraping_fields():
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=None)
    assert "site" not in lead
    assert "emails" not in lead
    assert "site" not in lead["proveniencia"]


def test_build_lead_json_with_enrichment_includes_scraping_fields_and_proveniencia():
    enrichment = EnrichmentResult(
        site="https://empresa.com.br/",
        site_matched=True,
        emails=[EmailVerification(email="contato@empresa.com.br", nivel=4, motivos=[])],
        telefones=["1134357093"],
        whatsapp=["5511999998888"],
        redes_sociais={"instagram": "https://instagram.com/empresa"},
    )
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=enrichment, enriquecido_em=2000.0)

    assert lead["site"] == "https://empresa.com.br/"
    assert lead["emails"][0]["valor"] == "contato@empresa.com.br"
    assert lead["emails"][0]["confianca"] == "alta"
    assert lead["whatsapp"] == ["5511999998888"]
    assert lead["redes_sociais"]["instagram"] == "https://instagram.com/empresa"
    assert lead["proveniencia"]["emails"]["timestamp"] == 2000.0
    assert lead["proveniencia"]["site"]["rota_ou_url"] == "https://empresa.com.br/"


def test_build_lead_json_skips_scraping_fields_when_site_not_matched():
    enrichment = EnrichmentResult(site="https://outrosite.com.br/", site_matched=False, erro="match_fraco")
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=enrichment)
    assert "site" not in lead
    assert "emails" not in lead


def test_enriquecimento_status_ok():
    enrichment = EnrichmentResult(site="https://empresa.com.br/", site_matched=True)
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=enrichment)
    assert lead["enriquecimento"] == {"status": "ok", "motivo": None}


def test_enriquecimento_status_requer_navegador():
    enrichment = EnrichmentResult(site="https://empresa.com.br/", site_matched=True, requer_navegador=True)
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=enrichment)
    assert lead["enriquecimento"] == {"status": "requer_navegador", "motivo": None}


def test_enriquecimento_status_match_fraco():
    enrichment = EnrichmentResult(site="https://outrosite.com.br/", site_matched=False, erro="match_fraco")
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=enrichment)
    assert lead["enriquecimento"] == {"status": "match_fraco", "motivo": "match_fraco"}


def test_enriquecimento_status_falha():
    enrichment = EnrichmentResult(site="https://empresa.com.br/", erro="ConnectError: timeout")
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=enrichment)
    assert lead["enriquecimento"] == {"status": "falha", "motivo": "ConnectError: timeout"}


def test_enriquecimento_status_falha_ao_extrair_contatos_com_site_confirmado():
    enrichment = EnrichmentResult(site="https://empresa.com.br/", site_matched=True, erro="falha_ao_extrair_contatos: X")
    lead = build_lead_json(_validacao(), _BREAKDOWN, enrichment=enrichment)
    assert lead["enriquecimento"]["status"] == "falha"


def test_sem_enrichment_nao_tem_campo_enriquecimento():
    assert "enriquecimento" not in build_lead_json(_validacao(), _BREAKDOWN)


def test_export_leads_caps_at_max_and_keeps_highest_scores():
    leads = [{"cnpj": str(i), "score": i} for i in range(150)]
    result = export_leads(leads, max_leads=100)
    assert result["total"] == 100
    assert result["leads"][0]["score"] == 149
    assert result["leads"][-1]["score"] == 50


def test_export_leads_below_cap_returns_all():
    leads = [{"cnpj": "1", "score": 10}, {"cnpj": "2", "score": 90}]
    result = export_leads(leads)
    assert result["total"] == 2
    assert result["leads"][0]["cnpj"] == "2"  # maior score primeiro
