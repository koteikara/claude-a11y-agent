# -*- coding: utf-8 -*-

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("bleach")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient

from a11y_runner.drive import InMemoryDriveStore
from a11y_runner.schema import CONFIG_TAB, JOBS_TAB, METRICS_TAB, REVIEW_TAB, SITES_TAB
from a11y_runner.sheets import InMemorySheetStore
from web.backend import app as app_module


def make_store() -> InMemorySheetStore:
    return InMemorySheetStore({
        CONFIG_TAB: [
            {"key": "drive_input_folder_id", "value": "input"},
            {"key": "drive_output_ai_folder_id", "value": "ai"},
            {"key": "drive_output_gold_folder_id", "value": "gold"},
            {"key": "default_site", "value": "saga-city"},
            {"key": "llm_provider", "value": "gemini"},
            {"key": "run_mode", "value": "batch"},
        ],
        SITES_TAB: [{"site": "saga-city", "body_xpath": "", "notes": ""}],
        JOBS_TAB: [{
            "job_id": "job-1", "site": "saga-city", "page_id": "sg001", "input_file": "", "provider": "", "priority": "",
            "status": "queued", "created_at": "2026-06-09T00:00:00+00:00", "started_at": "", "finished_at": "",
            "ai_output_link": "", "gold_output_link": "", "review_status": "", "reviewer": "", "promote_requested": "false", "error": "", "notes": "",
        }],
        REVIEW_TAB: [],
        METRICS_TAB: [],
    })


def make_client(monkeypatch, store, drive) -> TestClient:
    monkeypatch.setenv("AUTH_DISABLED_FOR_TESTS", "true")
    app_module.app.dependency_overrides[app_module.get_sheet_store] = lambda: store
    app_module.app.dependency_overrides[app_module.get_drive_store] = lambda: drive
    return TestClient(app_module.app)


def test_healthz_does_not_require_basic_auth(monkeypatch):
    monkeypatch.delenv("AUTH_DISABLED_FOR_TESTS", raising=False)
    monkeypatch.delenv("BASIC_AUTH_USERNAME", raising=False)
    monkeypatch.delenv("BASIC_AUTH_PASSWORD", raising=False)
    response = TestClient(app_module.app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_jobs_filter_and_run_updates_sheet_and_drive(monkeypatch):
    store = make_store()
    drive = InMemoryDriveStore({("input", "saga-city/sg001.html"): "<p>TEL <b>demo</b></p>"})
    client = make_client(monkeypatch, store, drive)

    response = client.get("/api/jobs?site=saga-city&status=queued")
    assert response.status_code == 200
    assert response.json()["jobs"][0]["job_id"] == "job-1"

    run_response = client.post("/api/jobs/job-1/run")
    assert run_response.status_code == 200
    job = store.rows[JOBS_TAB][0]
    assert job["status"] == "needs_review"
    assert ("ai", "saga-city/sg001.html") in drive.files
    assert store.rows[METRICS_TAB]
    assert store.rows[REVIEW_TAB]


def test_html_is_sanitized_and_diff_ignores_cms_attributes(monkeypatch):
    store = make_store()
    store.rows[JOBS_TAB][0].update({"status": "done", "ai_output_link": "drive://ai/saga-city/sg001.html"})
    drive = InMemoryDriveStore({
        ("input", "saga-city/sg001.html"): '<div id="ui-id-1" class="cmstag"><p onclick="evil()">Old</p><script>alert(1)</script></div>',
        ("ai", "saga-city/sg001.html"): '<div id="ui-id-2" class="cmstag"><p>New</p></div>',
        ("gold", "saga-city/sg001.html"): '<div id="ui-id-3" class="cmstag"><p>New</p></div>',
    })
    client = make_client(monkeypatch, store, drive)

    html_response = client.get("/api/jobs/job-1/html?stage=old")
    assert html_response.status_code == 200
    assert "<script" not in html_response.text
    assert "onclick" not in html_response.text

    diff = client.get("/api/jobs/job-1/diff").json()
    assert diff["old_ai"]["summary"]["changed"] > 0
    assert diff["ai_gold"]["summary"] == {"added": 0, "removed": 0, "changed": 0}


def test_approve_writes_gold_and_sheet_status(monkeypatch):
    store = make_store()
    store.rows[JOBS_TAB][0].update({"status": "done", "ai_output_link": "drive://ai/saga-city/sg001.html"})
    drive = InMemoryDriveStore({
        ("input", "saga-city/sg001.html"): "<p>old</p>",
        ("ai", "saga-city/sg001.html"): "<p>ai</p>",
    })
    client = make_client(monkeypatch, store, drive)

    response = client.post("/api/jobs/job-1/approve", json={"reviewer": "ops"})
    assert response.status_code == 200
    assert drive.files[("gold", "saga-city/sg001.html")] == "<p>ai</p>"
    assert store.rows[JOBS_TAB][0]["review_status"] == "approved"
    assert store.rows[JOBS_TAB][0]["reviewer"] == "ops"
