from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.scraping.contacts import discover_contacts
from scripts.scraping.context_signals import ContextSignals, detect_context_signals, parece_requer_js
from scripts.scraping.email_verify import EmailVerification, MXResolver, verify_email
from scripts.scraping.http import ScrapeSession, fetch
from scripts.scraping.site_discovery import validar_match


@dataclass
class EnrichmentResult:
    site: str | None = None
    site_matched: bool = False
    requer_navegador: bool = False
    emails: list[EmailVerification] = field(default_factory=list)
    telefones: list[str] = field(default_factory=list)
    whatsapp: list[str] = field(default_factory=list)
    redes_sociais: dict[str, str] = field(default_factory=dict)
    context: ContextSignals | None = None
    erro: str | None = None


async def enrich(
    candidate_url: str | None,
    session: ScrapeSession,
    *,
    cnpj: str,
    razao_social: str | None = None,
    nome_fantasia: str | None = None,
    telefone_cadastral: str | None = None,
    email_cadastral: str | None = None,
    mx_resolver: MXResolver | None = None,
    **fetch_kwargs: Any,
) -> EnrichmentResult:
    """S4 completo (4.1→4.4) para um único lead: busca a URL candidata (achada
    pelo skill via busca web — ver `site_discovery.py`), valida o match, e se
    confirmado, extrai contatos, verifica e-mails e coleta sinais de contexto.
    Se o scraping falhar em qualquer ponto, o lead continua existindo e
    utilizável — só com menos campos (premissa central do ARCTETURE.md).
    """
    if not candidate_url:
        return EnrichmentResult(erro="sem_site_candidato")

    try:
        home = await fetch(candidate_url, session, **fetch_kwargs)
    except Exception as exc:
        return EnrichmentResult(site=candidate_url, erro=f"{type(exc).__name__}: {exc}")

    match = validar_match(
        home["text"],
        cnpj=cnpj,
        razao_social=razao_social,
        nome_fantasia=nome_fantasia,
        telefone=telefone_cadastral,
    )
    if not match.matched:
        return EnrichmentResult(site=home["url"], site_matched=False, erro="match_fraco")

    if parece_requer_js(home["text"]):
        return EnrichmentResult(site=home["url"], site_matched=True, requer_navegador=True)

    try:
        contatos = await discover_contacts(home["url"], session, **fetch_kwargs)
    except Exception as exc:
        return EnrichmentResult(
            site=home["url"], site_matched=True, erro=f"falha_ao_extrair_contatos: {type(exc).__name__}: {exc}"
        )

    emails_verificados = [
        verify_email(email, found_on_official_site=True, email_cadastral=email_cadastral, mx_resolver=mx_resolver)
        for email in sorted(contatos.emails)
    ]
    context = detect_context_signals(home["text"])

    return EnrichmentResult(
        site=home["url"],
        site_matched=True,
        emails=emails_verificados,
        telefones=sorted(contatos.telefones),
        whatsapp=sorted(contatos.whatsapp),
        redes_sociais=contatos.redes_sociais,
        context=context,
    )
