from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from selectolax.parser import HTMLParser

from scripts.scraping.http import ScrapeSession, fetch

HIGH_SIGNAL_PATHS = ["/contato", "/contatos", "/sobre", "/sobre-nos", "/equipe", "/quem-somos", "/about", "/contact"]

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?:\+55\s?)?\(?\d{2}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}")
_WHATSAPP_LINK_RE = re.compile(r"(?:wa\.me|whatsapp\.com)/(?:send/?\?phone=)?(\d{8,15})")

SOCIAL_DOMAINS = {
    "instagram.com": "instagram",
    "facebook.com": "facebook",
    "linkedin.com": "linkedin",
    "twitter.com": "twitter",
    "x.com": "twitter",
    "tiktok.com": "tiktok",
    "youtube.com": "youtube",
}

# Nomes/cargos de decisores (seção 4.2 do ARCTETURE.md) não entram aqui: extrair
# pessoa+cargo de HTML livre com regex é pouco confiável, e é exatamente o tipo de
# interpretação que a "regra de ouro" da seção 6 delega ao Claude Code lendo o
# texto já limpo — não a um script. Este módulo entrega e-mail/telefone/WhatsApp/
# redes sociais, que são extraíveis de forma determinística.


@dataclass
class ContactExtraction:
    emails: set[str] = field(default_factory=set)
    telefones: set[str] = field(default_factory=set)
    whatsapp: set[str] = field(default_factory=set)
    redes_sociais: dict[str, str] = field(default_factory=dict)
    paginas_visitadas: list[str] = field(default_factory=list)


def _extract_social_links(tree: HTMLParser) -> dict[str, str]:
    redes: dict[str, str] = {}
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        host = urlparse(href).netloc.lower().removeprefix("www.")
        for domain, nome in SOCIAL_DOMAINS.items():
            if host == domain or host.endswith("." + domain):
                redes.setdefault(nome, href)
    return redes


def extract_contacts_from_html(html: str) -> ContactExtraction:
    """Extração determinística — deliberadamente NÃO usa trafilatura aqui: contato
    costuma morar no rodapé/cabeçalho, exatamente o que trafilatura remove por
    design (é feito pra extrair conteúdo editorial, não boilerplate).
    """
    tree = HTMLParser(html)
    texto = tree.text(separator=" ")

    emails = {m.lower() for m in _EMAIL_RE.findall(texto)}
    telefones = {re.sub(r"\D", "", m) for m in _PHONE_RE.findall(texto)}

    whatsapp: set[str] = set()
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        match = _WHATSAPP_LINK_RE.search(href)
        if match:
            whatsapp.add(match.group(1))

    redes = _extract_social_links(tree)
    return ContactExtraction(emails=emails, telefones=telefones, whatsapp=whatsapp, redes_sociais=redes)


def _candidate_urls(base_url: str, tree: HTMLParser) -> list[str]:
    candidatos: list[str] = []
    seen: set[str] = set()
    base_domain = urlparse(base_url).netloc
    for a in tree.css("a[href]"):
        href = a.attributes.get("href") or ""
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.netloc != base_domain:
            continue
        path = parsed.path.lower().rstrip("/")
        if full in seen:
            continue
        if any(path.endswith(p) for p in HIGH_SIGNAL_PATHS):
            seen.add(full)
            candidatos.append(full)
    return candidatos


async def discover_contacts(
    site_url: str,
    session: ScrapeSession,
    *,
    max_pages: int = 5,
    **fetch_kwargs,
) -> ContactExtraction:
    """4.2 — rastreia a home + páginas de alto sinal (`/contato`, `/sobre`,
    `/equipe`, `/quem-somos`, ...), até o teto de `max_pages` páginas no total
    (a home conta como uma). Extrai e-mails, telefones, WhatsApp e redes sociais.
    """
    resultado = ContactExtraction()

    home = await fetch(site_url, session, max_pages_per_domain=max_pages, **fetch_kwargs)
    resultado.paginas_visitadas.append(home["url"])
    tree = HTMLParser(home["text"])
    extraido = extract_contacts_from_html(home["text"])
    resultado.emails |= extraido.emails
    resultado.telefones |= extraido.telefones
    resultado.whatsapp |= extraido.whatsapp
    resultado.redes_sociais.update(extraido.redes_sociais)

    for url in _candidate_urls(home["url"], tree):
        if len(resultado.paginas_visitadas) >= max_pages:
            break
        try:
            pagina = await fetch(url, session, max_pages_per_domain=max_pages, **fetch_kwargs)
        except Exception:
            continue
        resultado.paginas_visitadas.append(pagina["url"])
        extraido = extract_contacts_from_html(pagina["text"])
        resultado.emails |= extraido.emails
        resultado.telefones |= extraido.telefones
        resultado.whatsapp |= extraido.whatsapp
        resultado.redes_sociais.update(extraido.redes_sociais)

    return resultado
