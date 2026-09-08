from scripts.scraping.context_signals import detect_context_signals, parece_requer_js


def test_detect_ecommerce_signal():
    html = "<html><body><button>Adicionar ao carrinho</button></body></html>"
    result = detect_context_signals(html)
    assert result.ecommerce is True


def test_detect_no_ecommerce_signal():
    html = "<html><body>Somos uma clínica odontológica.</body></html>"
    result = detect_context_signals(html)
    assert result.ecommerce is False


def test_detect_wordpress_fingerprint():
    html = '<html><head><link rel="stylesheet" href="/wp-content/themes/x/style.css"></head><body></body></html>'
    result = detect_context_signals(html)
    assert "wordpress" in result.tecnologias


def test_detect_no_fingerprint_when_absent():
    html = "<html><body>Site simples sem CMS conhecido.</body></html>"
    result = detect_context_signals(html)
    assert result.tecnologias == []


def test_indicios_equipe_counts_leadership_keywords():
    html = "<html><body>Nossa diretora é Fulana. O sócio-fundador é Beltrano.</body></html>"
    result = detect_context_signals(html)
    assert result.indicios_equipe >= 2


def test_parece_requer_js_true_for_spa_shell():
    html = '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'
    assert parece_requer_js(html) is True


def test_parece_requer_js_false_for_content_rich_page():
    html = "<html><body><div id=\"root\">" + ("Conteúdo institucional real da empresa. " * 20) + "</div></body></html>"
    assert parece_requer_js(html) is False


def test_parece_requer_js_false_without_spa_marker():
    html = "<html><body>Página curta mas sem marcador de SPA.</body></html>"
    assert parece_requer_js(html) is False
