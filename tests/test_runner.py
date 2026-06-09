# -*- coding: utf-8 -*-

from pathlib import Path

import pytest

from a11y_runner.drive import InMemoryDriveStore
from a11y_runner.models import PageResult, ReviewItem
from a11y_runner.runner import check_gold, dry_run, init_sheet, run_jobs
from a11y_runner.schema import CONFIG_TAB, JOBS_TAB, METRICS_TAB, REVIEW_TAB, RUNS_TAB, TAB_HEADERS
from a11y_runner.sheets import InMemorySheetStore


def test_init_sheet_is_idempotent_and_seeds_config():
    store = InMemorySheetStore()

    init_sheet(store)
    init_sheet(store)

    assert set(TAB_HEADERS).issubset(store.rows)
    config_keys = [row["key"] for row in store.rows[CONFIG_TAB]]
    assert config_keys.count("llm_provider") == 1
    assert "drive_input_folder_id" in config_keys


def test_dry_run_lists_queued_jobs_by_priority_and_site():
    store = _store_with_config()
    store.rows[JOBS_TAB] = [
        {"job_id": "done", "site": "saga-city", "page_id": "p3", "priority": "1", "status": "done"},
        {"job_id": "late", "site": "saga-city", "page_id": "p2", "priority": "20", "status": "queued"},
        {"job_id": "early", "site": "saga-city", "page_id": "p1", "priority": "5", "status": "queued"},
        {"job_id": "other", "site": "other", "page_id": "p0", "priority": "1", "status": "queued"},
    ]

    rows = dry_run(store, site="saga-city")

    assert [row["job_id"] for row in rows] == ["early", "late"]


def test_run_jobs_writes_ai_output_review_metrics_and_run_summary():
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-1",
        "site": "saga-city",
        "page_id": "sg00001",
        "input_file": "",
        "priority": "1",
        "status": "queued",
    }]
    drive = InMemoryDriveStore({("input", "saga-city/sg00001.html"): "<p>こちら TEL</p>"})

    def fake_engine(old_html, **kwargs):
        return PageResult(
            ai_html=old_html.replace("こちら", "申請案内"),
            mechanical_fixes=[{"rule_id": "sample"}],
            needs_review=[ReviewItem("advisory", "LINK-R-01", "指示語リンク", "こちら", "文言修正")],
            stats={"n_review": 1},
        )

    summary = run_jobs(store, drive, engine=fake_engine)

    assert summary["n_review"] == 1
    job = store.rows[JOBS_TAB][0]
    assert job["status"] == "needs_review"
    assert job["ai_output_link"] == "drive://ai/saga-city/sg00001.html"
    assert drive.files[("ai", "saga-city/sg00001.html")] == "<p>申請案内 TEL</p>"
    assert store.rows[REVIEW_TAB][0]["decision"] == "open"
    assert store.rows[METRICS_TAB][0]["n_mechanical_fixes"] == 1
    assert store.rows[RUNS_TAB][0]["n_review"] == 1


def test_run_jobs_records_error_and_continues():
    store = _store_with_config()
    store.rows[JOBS_TAB] = [
        {"job_id": "bad", "site": "saga-city", "page_id": "missing", "status": "queued"},
        {"job_id": "good", "site": "saga-city", "page_id": "ok", "status": "queued"},
    ]
    drive = InMemoryDriveStore({("input", "saga-city/ok.html"): "<p>ok</p>"})

    def fake_engine(old_html, **kwargs):
        return PageResult(ai_html=old_html)

    summary = run_jobs(store, drive, engine=fake_engine)

    assert summary["n_error"] == 1
    assert summary["n_done"] == 1
    assert store.rows[JOBS_TAB][0]["status"] == "error"
    assert store.rows[JOBS_TAB][1]["status"] == "done"


def test_check_gold_records_metrics_and_review_rows(tmp_path: Path):
    pytest.importorskip("lxml")
    pairs = tmp_path / "pairs.jsonl"
    pairs.write_text(
        '{"id":"saga-city-sg00001","site":"saga-city","page_id":"sg00001",'
        '"checks":[{"type":"no_anchor_text","value":["こちら"]},'
        '{"type":"no_attr","deny":["align"],"advisory":true}]}\n',
        encoding="utf-8",
    )
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-1",
        "site": "saga-city",
        "page_id": "sg00001",
        "status": "done",
    }]
    drive = InMemoryDriveStore({
        ("input", "saga-city/sg00001.html"): "<html><body><p>old</p></body></html>",
        ("gold", "saga-city/sg00001.html"): '<html><body><p align="left"><a href="/x">こちら</a></p></body></html>',
    })

    summary = check_gold(store, drive, pairs_path=pairs)

    assert summary["checks_failed"] == 1
    assert summary["advisory_hits"] == 1
    assert store.rows[METRICS_TAB][0]["checks_failed"] == 1
    assert [row["rule_id"] for row in store.rows[REVIEW_TAB]] == ["no_anchor_text", "no_attr"]


def _store_with_config():
    store = InMemorySheetStore()
    init_sheet(store)
    for row in store.rows[CONFIG_TAB]:
        if row["key"] == "drive_input_folder_id":
            row["value"] = "input"
        if row["key"] == "drive_output_ai_folder_id":
            row["value"] = "ai"
        if row["key"] == "drive_output_gold_folder_id":
            row["value"] = "gold"
    return store
