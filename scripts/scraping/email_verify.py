from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import dns.exception
import dns.resolver

DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "tempmail.com",
    "10minutemail.com",
    "guerrillamail.com",
    "yopmail.com",
    "trashmail.com",
}

GENERIC_PROVIDER_DOMAINS = {
    "gmail.com",
    "hotmail.com",
    "outlook.com",
    "yahoo.com",
    "yahoo.com.br",
    "icloud.com",
    "live.com",
    "bol.com.br",
    "uol.com.br",
    "terra.com.br",
}

GENERIC_LOCAL_PARTS = {
    "contato",
    "contatos",
    "info",
    "sac",
    "vendas",
    "comercial",
    "atendimento",
    "suporte",
    "financeiro",
    "rh",
    "admin",
    "geral",
    "faleconosco",
    "no-reply",
    "noreply",
}

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

NIVEL_CONFIANCA = {
    0: "invalido",
    1: "baixa",
    2: "media",
    3: "boa",
    4: "alta",
    5: "alta_nominal",
}

MXResolver = Callable[[str], Sequence[object]]


@dataclass
class EmailVerification:
    email: str
    nivel: int  # 0 (inválido) a 5, escada da seção 4.3 do ARCTETURE.md
    cruzamento_cadastral: bool = False
    motivos: list[str] = field(default_factory=list)

    @property
    def confianca(self) -> str:
        if self.cruzamento_cadastral:
            return "maxima"
        return NIVEL_CONFIANCA[self.nivel]


def _sintaxe_valida(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _dominio(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


def _resolver_mx_real(dominio: str) -> Sequence[object]:
    return list(dns.resolver.resolve(dominio, "MX"))


def _tem_mx(dominio: str, resolver: MXResolver) -> bool:
    try:
        return bool(resolver(dominio))
    except (dns.exception.DNSException, OSError):
        return False


def verify_email(
    email: str,
    *,
    found_on_official_site: bool = False,
    email_cadastral: str | None = None,
    mx_resolver: MXResolver | None = None,
) -> EmailVerification:
    """Escada de confiança da seção 4.3 do ARCTETURE.md, sem custo e sem SMTP
    handshake: 1 sintaxe → 2 domínio não-descartável/não-genérico → 3 MX → 4
    publicado no site oficial → 5 nominal. O nível "+" (máxima confiança) é o
    cruzamento com o e-mail cadastral do BaseCNPJ, independente do nível 1-5.
    """
    resolver = mx_resolver or _resolver_mx_real
    email_normalizado = email.strip()

    if not _sintaxe_valida(email_normalizado):
        return EmailVerification(email=email_normalizado, nivel=0, motivos=["sintaxe_invalida"])

    motivos = ["sintaxe_valida"]
    dominio = _dominio(email_normalizado)
    nivel = 1

    dominio_ok = dominio not in DISPOSABLE_DOMAINS and dominio not in GENERIC_PROVIDER_DOMAINS
    if dominio_ok:
        nivel = 2
        motivos.append("dominio_nao_descartavel_nem_generico")
    elif dominio in DISPOSABLE_DOMAINS:
        motivos.append("dominio_descartavel")
    else:
        motivos.append("dominio_provedor_generico")

    if nivel >= 2 and _tem_mx(dominio, resolver):
        nivel = 3
        motivos.append("mx_confirmado")

    if nivel >= 3 and found_on_official_site:
        nivel = 4
        motivos.append("publicado_no_site_oficial")

    local_part = email_normalizado.split("@", 1)[0].lower()
    eh_nominal = local_part not in GENERIC_LOCAL_PARTS
    if nivel >= 4 and eh_nominal:
        nivel = 5
        motivos.append("nominal")

    cruzamento = bool(email_cadastral) and email_normalizado.lower() == email_cadastral.strip().lower()
    if cruzamento:
        motivos.append("cruzamento_cadastral_basecnpj")

    return EmailVerification(email=email_normalizado, nivel=nivel, cruzamento_cadastral=cruzamento, motivos=motivos)
