from scripts.scraping.email_verify import verify_email

_MX_OK = lambda dominio: ["mx1.exemplo.com"]  # noqa: E731
_MX_SEM_REGISTRO = lambda dominio: []  # noqa: E731


def test_sintaxe_invalida_fica_no_nivel_zero():
    result = verify_email("nao-e-email", mx_resolver=_MX_OK)
    assert result.nivel == 0
    assert result.confianca == "invalido"


def test_provedor_generico_trava_no_nivel_um():
    result = verify_email("fulano@gmail.com", mx_resolver=_MX_OK)
    assert result.nivel == 1
    assert result.confianca == "baixa"


def test_dominio_descartavel_trava_no_nivel_um():
    result = verify_email("fulano@mailinator.com", mx_resolver=_MX_OK)
    assert result.nivel == 1
    assert "dominio_descartavel" in result.motivos


def test_dominio_proprio_sem_mx_fica_no_nivel_dois():
    result = verify_email("contato@empresa.com.br", mx_resolver=_MX_SEM_REGISTRO)
    assert result.nivel == 2
    assert result.confianca == "media"


def test_dominio_proprio_com_mx_sobe_para_nivel_tres():
    result = verify_email("contato@empresa.com.br", mx_resolver=_MX_OK)
    assert result.nivel == 3
    assert result.confianca == "boa"


def test_publicado_no_site_oficial_sobe_para_nivel_quatro():
    result = verify_email("contato@empresa.com.br", found_on_official_site=True, mx_resolver=_MX_OK)
    assert result.nivel == 4
    assert result.confianca == "alta"


def test_local_part_generico_nao_sobe_para_nivel_cinco_mesmo_publicado():
    result = verify_email("contato@empresa.com.br", found_on_official_site=True, mx_resolver=_MX_OK)
    assert result.nivel == 4  # "contato" é genérico, não nominal


def test_local_part_nominal_sobe_para_nivel_cinco():
    result = verify_email("luis.henrique@empresa.com.br", found_on_official_site=True, mx_resolver=_MX_OK)
    assert result.nivel == 5
    assert result.confianca == "alta_nominal"


def test_cruzamento_com_cadastral_e_confianca_maxima_independente_do_nivel():
    result = verify_email(
        "contato@empresa.com.br",
        mx_resolver=_MX_SEM_REGISTRO,  # nível ficaria em 2
        email_cadastral="CONTATO@empresa.com.br",
    )
    assert result.cruzamento_cadastral is True
    assert result.confianca == "maxima"
    assert result.nivel == 2  # o nível-base não muda, só a confiança reportada


def test_cruzamento_nao_acontece_com_cadastral_diferente():
    result = verify_email("contato@empresa.com.br", mx_resolver=_MX_OK, email_cadastral="outro@empresa.com.br")
    assert result.cruzamento_cadastral is False
    assert result.confianca == "boa"
