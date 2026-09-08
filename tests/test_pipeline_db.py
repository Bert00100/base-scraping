from scripts.pipeline import db


def test_make_run_id_is_deterministic_and_order_independent():
    a = db.make_run_id({"nicho": "dentista", "uf": "SP"})
    b = db.make_run_id({"uf": "SP", "nicho": "dentista"})
    c = db.make_run_id({"nicho": "dentista", "uf": "RJ"})
    assert a == b
    assert a != c


def test_ensure_run_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "pipeline.sqlite3")
    run_id = db.make_run_id({"nicho": "dentista"})
    db.ensure_run(conn, run_id, {"nicho": "dentista"}, target_leads=100, now=0)
    db.ensure_run(conn, run_id, {"nicho": "dentista"}, target_leads=100, now=999)  # não deve sobrescrever

    row = conn.execute("SELECT created_at FROM runs WHERE run_id=?", (run_id,)).fetchone()
    assert row["created_at"] == 0


def test_upsert_and_get_lead_roundtrip(tmp_path):
    conn = db.connect(tmp_path / "pipeline.sqlite3")
    run_id = "run1"
    db.upsert_lead(
        conn, run_id, "00000000000191", status="descoberto", discovery={"razao_social": "BANCO DO BRASIL"}
    )
    lead = db.get_lead(conn, run_id, "00000000000191")
    assert lead["status"] == "descoberto"
    assert lead["discovery"] == {"razao_social": "BANCO DO BRASIL"}
    assert lead["detalhe"] is None


def test_upsert_lead_preserves_discovery_when_updating_with_detalhe_only(tmp_path):
    conn = db.connect(tmp_path / "pipeline.sqlite3")
    run_id = "run1"
    db.upsert_lead(conn, run_id, "123", status="descoberto", discovery={"razao_social": "X"})
    db.upsert_lead(conn, run_id, "123", status="validado", detalhe={"situacao": "ativa"})

    lead = db.get_lead(conn, run_id, "123")
    assert lead["status"] == "validado"
    assert lead["discovery"] == {"razao_social": "X"}
    assert lead["detalhe"] == {"situacao": "ativa"}


def test_list_and_count_leads_filter_by_status(tmp_path):
    conn = db.connect(tmp_path / "pipeline.sqlite3")
    run_id = "run1"
    db.upsert_lead(conn, run_id, "1", status="validado")
    db.upsert_lead(conn, run_id, "2", status="validado")
    db.upsert_lead(conn, run_id, "3", status="descartado", discard_reason="situacao != ativa")

    assert db.count_leads(conn, run_id) == 3
    assert db.count_leads(conn, run_id, status="validado") == 2
    assert len(db.list_leads(conn, run_id, status="descartado")) == 1
    assert db.list_leads(conn, run_id, status="descartado")[0]["discard_reason"] == "situacao != ativa"


def test_checkpoint_defaults_to_page_one_and_persists(tmp_path):
    conn = db.connect(tmp_path / "pipeline.sqlite3")
    run_id = "run1"

    assert db.get_checkpoint(conn, run_id, "8630504") == {"next_page": 1, "exhausted": False}

    db.save_checkpoint(conn, run_id, "8630504", next_page=5)
    assert db.get_checkpoint(conn, run_id, "8630504") == {"next_page": 5, "exhausted": False}

    db.save_checkpoint(conn, run_id, "8630504", next_page=9, exhausted=True)
    assert db.get_checkpoint(conn, run_id, "8630504") == {"next_page": 9, "exhausted": True}


def test_checkpoints_are_independent_per_cnae(tmp_path):
    conn = db.connect(tmp_path / "pipeline.sqlite3")
    run_id = "run1"
    db.save_checkpoint(conn, run_id, "8630504", next_page=3)
    db.save_checkpoint(conn, run_id, "4520000", next_page=7)

    assert db.get_checkpoint(conn, run_id, "8630504")["next_page"] == 3
    assert db.get_checkpoint(conn, run_id, "4520000")["next_page"] == 7
