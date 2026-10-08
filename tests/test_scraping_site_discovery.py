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



def test_validar_match_nao_junta_numeros_soltos_em_telefone():
    html = "<html><body><p>11</p><p>3435</p><p>7093</p></body></html>"
    result = validar_match(html, cnpj="00000000000000", telefone="(11) 34357093")
    assert result.matched is False
    assert "telefone" not in result.sinais


def test_validar_match_nao_junta_numeros_soltos_em_cnpj():
    html = "<html><body><span>43292842</span> <b>0001</b><b>77</b> <i>x</i>43292842<u>000177</u></body></html>"
    result = validar_match(html, cnpj="43292842000177")
    assert result.matched is False
    assert "cnpj" not in result.sinais


def test_validar_match_telefone_sem_ddd_exige_trecho_terminando_nele():
    html = "<html><body>Ligue: (11) 3435-7093</body></html>"
    assert validar_match(html, cnpj="00000000000000", telefone="3435-7093").matched is True
    html_meio = "<html><body>Protocolo 3435709355</body></html>"
    assert validar_match(html_meio, cnpj="00000000000000", telefone="34357093").matched is False
