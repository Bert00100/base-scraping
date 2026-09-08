from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(".cache/pipeline.sqlite3")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    params_json TEXT NOT NULL,
    target_leads INTEGER NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    run_id TEXT NOT NULL,
    cnpj TEXT NOT NULL,
    status TEXT NOT NULL,
    discovery_json TEXT,
    detalhe_json TEXT,
    discard_reason TEXT,
    updated_at REAL NOT NULL,
    PRIMARY KEY (run_id, cnpj)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    run_id TEXT NOT NULL,
    cnae TEXT NOT NULL,
    next_page INTEGER NOT NULL,
    exhausted INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (run_id, cnae)
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """SQLite é storage interno de checkpoint do pipeline — nunca o formato de saída (seção 11)."""
    path = db_path if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def make_run_id(params: dict[str, Any]) -> str:
    """ID determinístico a partir dos parâmetros do ICP — mesma consulta = mesma execução, permite retomar."""
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def ensure_run(
    conn: sqlite3.Connection,
    run_id: str,
    params: dict[str, Any],
    target_leads: int,
    *,
    now: float | None = None,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO runs (run_id, params_json, target_leads, created_at) VALUES (?, ?, ?, ?)",
        (run_id, json.dumps(params, default=str), target_leads, now if now is not None else time.time()),
    )
    conn.commit()


def upsert_lead(
    conn: sqlite3.Connection,
    run_id: str,
    cnpj: str,
    *,
    status: str,
    discovery: dict[str, Any] | None = None,
    detalhe: dict[str, Any] | None = None,
    discard_reason: str | None = None,
    now: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO leads (run_id, cnpj, status, discovery_json, detalhe_json, discard_reason, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id, cnpj) DO UPDATE SET
            status=excluded.status,
            discovery_json=COALESCE(excluded.discovery_json, leads.discovery_json),
            detalhe_json=COALESCE(excluded.detalhe_json, leads.detalhe_json),
            discard_reason=excluded.discard_reason,
            updated_at=excluded.updated_at
        """,
        (
            run_id,
            cnpj,
            status,
            json.dumps(discovery, default=str) if discovery is not None else None,
            json.dumps(detalhe, default=str) if detalhe is not None else None,
            discard_reason,
            now if now is not None else time.time(),
        ),
    )
    conn.commit()


def _row_to_lead(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "cnpj": row["cnpj"],
        "status": row["status"],
        "discovery": json.loads(row["discovery_json"]) if row["discovery_json"] else None,
        "detalhe": json.loads(row["detalhe_json"]) if row["detalhe_json"] else None,
        "discard_reason": row["discard_reason"],
    }


def get_lead(conn: sqlite3.Connection, run_id: str, cnpj: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM leads WHERE run_id=? AND cnpj=?", (run_id, cnpj)).fetchone()
    return _row_to_lead(row) if row is not None else None


def list_leads(conn: sqlite3.Connection, run_id: str, *, status: str | None = None) -> list[dict[str, Any]]:
    if status is None:
        rows = conn.execute("SELECT * FROM leads WHERE run_id=?", (run_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM leads WHERE run_id=? AND status=?", (run_id, status)).fetchall()
    return [_row_to_lead(row) for row in rows]


def count_leads(conn: sqlite3.Connection, run_id: str, *, status: str | None = None) -> int:
    if status is None:
        row = conn.execute("SELECT COUNT(*) AS c FROM leads WHERE run_id=?", (run_id,)).fetchone()
    else:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM leads WHERE run_id=? AND status=?", (run_id, status)
        ).fetchone()
    return row["c"]


def get_checkpoint(conn: sqlite3.Connection, run_id: str, cnae: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM checkpoints WHERE run_id=? AND cnae=?", (run_id, cnae)).fetchone()
    if row is None:
        return {"next_page": 1, "exhausted": False}
    return {"next_page": row["next_page"], "exhausted": bool(row["exhausted"])}


def save_checkpoint(
    conn: sqlite3.Connection, run_id: str, cnae: str, next_page: int, *, exhausted: bool = False
) -> None:
    conn.execute(
        """
        INSERT INTO checkpoints (run_id, cnae, next_page, exhausted) VALUES (?, ?, ?, ?)
        ON CONFLICT(run_id, cnae) DO UPDATE SET next_page=excluded.next_page, exhausted=excluded.exhausted
        """,
        (run_id, cnae, next_page, int(exhausted)),
    )
    conn.commit()
