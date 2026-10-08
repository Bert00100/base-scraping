from __future__ import annotations

import sqlite3
from typing import Any

import httpx

from scripts.basecnpj import routes
from scripts.basecnpj.config import Settings
from scripts.utils import only_digits

from . import db as db_module
from .icp import ICP


async def discover(
    icp: ICP,
    *,
    conn: sqlite3.Connection,
    run_id: str,
    target_leads: int = 100,
    per_page: int = 15,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[dict[str, Any]]:
    """S1 — pagina `route=avancada` por CNAE, sequencialmente (nunca em paralelo,
    ver seção 9 do ARCTETURE.md), até esgotar ou atingir o teto global de
    `target_leads` leads únicos por CNPJ nesta execução (`run_id`). Dedup entre
    CNAEs é automático: a chave primária da tabela `leads` é (run_id, cnpj).
    Checkpoint por página em `db.py` permite retomar de onde parou.
    """
    if icp.needs_confirmation:
        raise ValueError(
            f"ICP para nicho '{icp.nicho}' não tem CNAE resolvido — confirme com o usuário antes de descobrir."
        )

    for cnae in icp.cnaes:
        if db_module.count_leads(conn, run_id) >= target_leads:
            break

        checkpoint = db_module.get_checkpoint(conn, run_id, cnae)
        if checkpoint["exhausted"]:
            continue

        page = checkpoint["next_page"]
        while True:
            filtros = icp.filtros_por_cnae(cnae)
            resposta = await routes.avancada(
                **filtros, page=page, per_page=per_page, settings=settings, client=client
            )
            items = resposta.get("items", [])

            target_reached = False
            for item in items:
                if db_module.count_leads(conn, run_id) >= target_leads:
                    target_reached = True
                    break
                cnpj_key = only_digits(item.get("cnpj_completo", ""))
                if not cnpj_key:
                    continue
                db_module.upsert_lead(conn, run_id, cnpj_key, status="descoberto", discovery=item)

            if target_reached:
                # não terminamos de processar esta página — checkpoint fica nela mesma
                db_module.save_checkpoint(conn, run_id, cnae, page)
                return db_module.list_leads(conn, run_id, status="descoberto")

            total_pages = resposta.get("total_pages", page)
            if not items or page >= total_pages:
                db_module.save_checkpoint(conn, run_id, cnae, page + 1, exhausted=True)
                break

            page += 1
            db_module.save_checkpoint(conn, run_id, cnae, page)

    return db_module.list_leads(conn, run_id, status="descoberto")
