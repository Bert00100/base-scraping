from scripts.scraping.site_discovery import validar_match


def test_validar_match_finds_cnpj_in_footer():
    html = "<html><body><footer>CNPJ: 43.292.842/0001-77</footer></body></html>"
    result = validar_match(html, cnpj="43292842000177")
    assert result.matched is True
    assert "cnpj" in result.sinais


def test_validar_match_finds_razao_social():
    html = "<html><body><h1>Bem-vindo à Clinica Odontologica Quiles Ltda</h1></body></html>"
    result = validar_match(html, cnpj="00000000000000", razao_social="CLINICA ODONTOLOGICA QUILES LTDA")
    assert result.matched is True
    assert "razao_social" in result.sinais


def test_validar_match_finds_telefone():
    html = "<html><body>Ligue: (11) 3435-7093</body></html>"
    result = validar_match(html, cnpj="00000000000000", telefone="(11) 34357093")
    assert result.matched is True
    assert "telefone" in result.sinais


def test_validar_match_no_signal_is_weak_match():
    html = "<html><body>Site institucional genérico sem nenhum dado da empresa.</body></html>"
    result = validar_match(
        html, cnpj="43292842000177", razao_social="OUTRA EMPRESA LTDA", nome_fantasia="Outra", telefone="1199999999"
    )
    assert result.matched is False
    assert result.sinais == []

