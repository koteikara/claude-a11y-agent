# -*- coding: utf-8 -*-

from pathlib import Path

import pytest
import requests

from a11y_runner.drive import InMemoryDriveStore
from a11y_runner.models import PageResult, ReviewItem
from a11y_runner.runner import check_gold, dry_run, init_sheet, promote_requested_gold, run_jobs
from a11y_runner.schema import CONFIG_TAB, JOBS_TAB, METRICS_TAB, REVIEW_TAB, RUNS_TAB, SITES_TAB, TAB_HEADERS
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


def test_run_jobs_fetches_url_input_and_extracts_job_body_xpath(monkeypatch):
    store = _store_with_config()
    for row in store.rows[CONFIG_TAB]:
        if row["key"] == "body_xpath":
            row["value"] = '//*[@id="config-body"]'
    store.rows[JOBS_TAB] = [{
        "job_id": "test-url-001",
        "site": "saga-city",
        "page_id": "test-url-001",
        "input_file": "https://www.example.jp/sample/page.html",
        "body_xpath": '//*[@id="contents-in"]',
        "provider": "gemini",
        "priority": "1",
        "status": "queued",
    }]
    drive = InMemoryDriveStore({})
    calls = []
    captured = {}

    class Response:
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        content = (
            '<html><body><header>ヘッダー</header><main id="contents-in"><p>URL入力</p></main>'
            '<section id="config-body">Configではない</section><footer>フッター</footer></body></html>'
        ).encode("utf-8")

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr("a11y_runner.runner.requests.get", fake_get)

    def fake_engine(old_html, **kwargs):
        captured["old_html"] = old_html
        captured["body_xpath"] = kwargs["body_xpath"]
        return PageResult(ai_html=old_html.replace("URL入力", "URL入力 修正済み"))

    summary = run_jobs(store, drive, engine=fake_engine)

    expected_old = '<main id="contents-in"><p>URL入力</p></main>'
    assert summary["n_done"] == 1
    assert calls == [("https://www.example.jp/sample/page.html", {
        "timeout": 20.0,
        "headers": {"User-Agent": "claude-a11y-agent/1.0"},
    })]
    assert captured == {"old_html": expected_old, "body_xpath": '//*[@id="contents-in"]'}
    assert drive.files[("input", "saga-city/test-url-001.html")] == expected_old
    assert drive.files[("ai", "saga-city/test-url-001.html")] == '<main id="contents-in"><p>URL入力 修正済み</p></main>'
    assert store.rows[JOBS_TAB][0]["status"] == "done"


def test_run_jobs_uses_config_body_xpath_for_url_input(monkeypatch):
    store = _store_with_config()
    for row in store.rows[CONFIG_TAB]:
        if row["key"] == "body_xpath":
            row["value"] = '//*[@id="contents-in"]'
    store.rows[JOBS_TAB] = [{
        "job_id": "job-config-xpath",
        "site": "saga-city",
        "page_id": "config-xpath",
        "input_file": "https://www.example.jp/sample/page.html",
        "body_xpath": "",
        "status": "queued",
    }]
    drive = InMemoryDriveStore({})
    captured = {}

    class Response:
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        content = b'<html><body><nav>nav</nav><div id="contents-in"><p>Config XPath</p></div></body></html>'

        def raise_for_status(self):
            return None

    monkeypatch.setattr("a11y_runner.runner.requests.get", lambda *args, **kwargs: Response())

    def fake_engine(old_html, **kwargs):
        captured["old_html"] = old_html
        captured["body_xpath"] = kwargs["body_xpath"]
        return PageResult(ai_html=old_html)

    summary = run_jobs(store, drive, engine=fake_engine)

    assert summary["n_done"] == 1
    assert captured == {"old_html": '<div id="contents-in"><p>Config XPath</p></div>', "body_xpath": '//*[@id="contents-in"]'}


def test_run_jobs_uses_body_element_for_url_input_without_body_xpath(monkeypatch):
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-body-default",
        "site": "saga-city",
        "page_id": "body-default",
        "input_file": "https://www.example.jp/sample/page.html",
        "status": "queued",
    }]
    drive = InMemoryDriveStore({})
    captured = {}

    class Response:
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        content = b'<html><body><p>Body default</p></body></html>'

        def raise_for_status(self):
            return None

    monkeypatch.setattr("a11y_runner.runner.requests.get", lambda *args, **kwargs: Response())

    def fake_engine(old_html, **kwargs):
        captured["old_html"] = old_html
        captured["body_xpath"] = kwargs["body_xpath"]
        return PageResult(ai_html=old_html)

    summary = run_jobs(store, drive, engine=fake_engine)

    assert summary["n_done"] == 1
    assert captured == {"old_html": "<body><p>Body default</p></body>", "body_xpath": None}


def test_run_jobs_records_error_when_url_body_xpath_does_not_match(monkeypatch):
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-xpath-error",
        "site": "saga-city",
        "page_id": "xpath-error",
        "input_file": "https://www.example.jp/sample/page.html",
        "body_xpath": '//*[@id="missing"]',
        "status": "queued",
    }]
    drive = InMemoryDriveStore({})

    class Response:
        encoding = "utf-8"
        apparent_encoding = "utf-8"
        content = b'<html><body><main id="contents-in"><p>ok</p></main></body></html>'

        def raise_for_status(self):
            return None

    monkeypatch.setattr("a11y_runner.runner.requests.get", lambda *args, **kwargs: Response())

    summary = run_jobs(store, drive, engine=lambda old_html, **kwargs: PageResult(ai_html=old_html))

    assert summary["n_error"] == 1
    job = store.rows[JOBS_TAB][0]
    assert job["status"] == "error"
    assert 'RunnerError: body_xpath did not match any element: //*[@id="missing"]' in job["error"]


def test_run_jobs_keeps_drive_input_for_non_url_input_file(monkeypatch):
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-drive",
        "site": "saga-city",
        "page_id": "custom",
        "input_file": "saga-city/custom-input.html",
        "body_xpath": '//*[@id="ignored-for-drive-read"]',
        "status": "queued",
    }]
    drive = InMemoryDriveStore({("input", "saga-city/custom-input.html"): "<p>Drive入力</p>"})

    def fail_get(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("URL fetch should not be called for Drive input files")

    monkeypatch.setattr("a11y_runner.runner.requests.get", fail_get)

    def fake_engine(old_html, **kwargs):
        return PageResult(ai_html=old_html.replace("Drive入力", "Drive入力 修正済み"))

    summary = run_jobs(store, drive, engine=fake_engine)

    assert summary["n_done"] == 1
    assert drive.files[("ai", "saga-city/custom.html")] == "<p>Drive入力 修正済み</p>"
    assert store.rows[JOBS_TAB][0]["status"] == "done"


def test_run_jobs_records_error_when_url_page_id_is_blank(monkeypatch):
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-url-blank-page",
        "site": "saga-city",
        "page_id": "",
        "input_file": "https://www.example.jp/sample/page.html",
        "status": "queued",
    }]
    drive = InMemoryDriveStore({})

    def fail_get(*args, **kwargs):  # pragma: no cover - assertion helper
        raise AssertionError("URL fetch should not be called without page_id")

    monkeypatch.setattr("a11y_runner.runner.requests.get", fail_get)

    summary = run_jobs(store, drive, engine=lambda old_html, **kwargs: PageResult(ai_html=old_html))

    assert summary["n_error"] == 1
    job = store.rows[JOBS_TAB][0]
    assert job["status"] == "error"
    assert "RunnerError: site and page_id are required" in job["error"]


def test_run_jobs_records_url_fetch_error(monkeypatch):
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-url-error",
        "site": "saga-city",
        "page_id": "url-error",
        "input_file": "https://www.example.jp/missing.html",
        "status": "queued",
    }]
    drive = InMemoryDriveStore({})

    def fake_get(url, **kwargs):
        raise requests.exceptions.Timeout("connect timed out")

    monkeypatch.setattr("a11y_runner.runner.requests.get", fake_get)

    summary = run_jobs(store, drive, engine=lambda old_html, **kwargs: PageResult(ai_html=old_html))

    assert summary["n_error"] == 1
    job = store.rows[JOBS_TAB][0]
    assert job["status"] == "error"
    assert "RunnerError: URL fetch timed out after 20s" in job["error"]
    assert "https://www.example.jp/missing.html" in job["error"]


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


def test_promote_requested_gold_copies_approved_ai_to_gold():
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-1",
        "site": "saga-city",
        "page_id": "sg00001",
        "status": "needs_review",
        "review_status": "approved",
        "promote_requested": "true",
    }]
    drive = InMemoryDriveStore({("ai", "saga-city/sg00001.html"): "<p>approved</p>"})

    promoted = promote_requested_gold(store, drive)

    assert promoted == 1
    assert drive.files[("gold", "saga-city/sg00001.html")] == "<p>approved</p>"
    assert store.rows[JOBS_TAB][0]["gold_output_link"] == "drive://gold/saga-city/sg00001.html"
    assert store.rows[JOBS_TAB][0]["promote_requested"] == "false"


def test_run_jobs_promotes_approved_rows_even_without_queued_jobs():
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "job-1",
        "site": "saga-city",
        "page_id": "sg00001",
        "status": "done",
        "review_status": "approved",
        "promote_requested": "true",
    }]
    drive = InMemoryDriveStore({("ai", "saga-city/sg00001.html"): "<p>approved</p>"})

    summary = run_jobs(store, drive)

    assert summary["n_total"] == 0
    assert summary["n_promoted"] == 1
    assert drive.files[("gold", "saga-city/sg00001.html")] == "<p>approved</p>"


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


def test_run_jobs_fetches_url_and_uses_job_body_xpath(monkeypatch):
    store = _store_with_config()
    _set_config(store, "body_xpath", "//*[@id='config']")
    store.rows[SITES_TAB] = [{"site": "saga-city", "body_xpath": "//*[@id='site']", "notes": ""}]
    store.rows[JOBS_TAB] = [{
        "job_id": "url-job",
        "site": "saga-city",
        "page_id": "url-page",
        "input_file": "https://www.example.jp/sample/page.html",
        "body_xpath": "//*[@id='job']",
        "status": "queued",
    }]
    drive = InMemoryDriveStore({})
    calls = []
    seen = {}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return _FakeResponse('<html><body><main id="job">本文</main><main id="site">サイト</main></body></html>')

    def fake_engine(old_html, **kwargs):
        seen["old_html"] = old_html
        seen["body_xpath"] = kwargs["body_xpath"]
        return PageResult(ai_html=old_html)

    monkeypatch.setattr("a11y_runner.runner.requests.get", fake_get)

    summary = run_jobs(store, drive, engine=fake_engine)

    assert summary["n_done"] == 1
    assert calls[0][0] == "https://www.example.jp/sample/page.html"
    assert calls[0][1]["timeout"] > 0
    assert calls[0][1]["headers"]["User-Agent"]
    assert seen["body_xpath"] == "//*[@id='job']"
    assert seen["old_html"] == '<main id="job">本文</main>'
    assert drive.files[("ai", "saga-city/url-page.html")] == '<main id="job">本文</main>'


def test_run_jobs_uses_site_body_xpath_when_job_body_xpath_empty(monkeypatch):
    store = _store_with_config()
    _set_config(store, "body_xpath", "//*[@id='config']")
    store.rows[SITES_TAB] = [{"site": "saga-city", "body_xpath": "//*[@id='site']", "notes": ""}]
    store.rows[JOBS_TAB] = [{
        "job_id": "url-job",
        "site": "saga-city",
        "page_id": "url-page",
        "input_file": "https://www.example.jp/sample/page.html",
        "body_xpath": "",
        "status": "queued",
    }]
    seen = {}

    monkeypatch.setattr(
        "a11y_runner.runner.requests.get",
        lambda *args, **kwargs: _FakeResponse('<html><body><main id="site">サイト</main></body></html>'),
    )

    def fake_engine(old_html, **kwargs):
        seen.update(old_html=old_html, body_xpath=kwargs["body_xpath"])
        return PageResult(ai_html=old_html)

    run_jobs(store, InMemoryDriveStore({}), engine=fake_engine)

    assert seen == {"old_html": '<main id="site">サイト</main>', "body_xpath": "//*[@id='site']"}


def test_run_jobs_uses_config_body_xpath_when_job_and_site_empty(monkeypatch):
    store = _store_with_config()
    _set_config(store, "body_xpath", "//*[@id='config']")
    store.rows[SITES_TAB] = [{"site": "saga-city", "body_xpath": "", "notes": ""}]
    store.rows[JOBS_TAB] = [{
        "job_id": "url-job",
        "site": "saga-city",
        "page_id": "url-page",
        "input_file": "https://www.example.jp/sample/page.html",
        "status": "queued",
    }]
    seen = {}

    monkeypatch.setattr(
        "a11y_runner.runner.requests.get",
        lambda *args, **kwargs: _FakeResponse('<html><body><main id="config">設定</main></body></html>'),
    )

    def fake_engine(old_html, **kwargs):
        seen.update(old_html=old_html, body_xpath=kwargs["body_xpath"])
        return PageResult(ai_html=old_html)

    run_jobs(store, InMemoryDriveStore({}), engine=fake_engine)

    assert seen == {"old_html": '<main id="config">設定</main>', "body_xpath": "//*[@id='config']"}


def test_run_jobs_uses_body_element_when_body_xpath_unspecified(monkeypatch):
    store = _store_with_config()
    store.rows[SITES_TAB] = [{"site": "saga-city", "body_xpath": "", "notes": ""}]
    store.rows[JOBS_TAB] = [{
        "job_id": "url-job",
        "site": "saga-city",
        "page_id": "url-page",
        "input_file": "https://www.example.jp/sample/page.html",
        "status": "queued",
    }]
    seen = {}

    monkeypatch.setattr(
        "a11y_runner.runner.requests.get",
        lambda *args, **kwargs: _FakeResponse('<html><head><title>x</title></head><body><p>本文</p></body></html>'),
    )

    def fake_engine(old_html, **kwargs):
        seen.update(old_html=old_html, body_xpath=kwargs["body_xpath"])
        return PageResult(ai_html=old_html)

    run_jobs(store, InMemoryDriveStore({}), engine=fake_engine)

    assert seen == {"old_html": "<body><p>本文</p></body>", "body_xpath": None}


def test_run_jobs_records_error_when_body_xpath_not_found(monkeypatch):
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "url-job",
        "site": "saga-city",
        "page_id": "url-page",
        "input_file": "https://www.example.jp/sample/page.html",
        "body_xpath": "//*[@id='missing']",
        "status": "queued",
    }]

    monkeypatch.setattr(
        "a11y_runner.runner.requests.get",
        lambda *args, **kwargs: _FakeResponse('<html><body><main id="contents">本文</main></body></html>'),
    )

    summary = run_jobs(store, InMemoryDriveStore({}), engine=lambda old_html, **kwargs: PageResult(ai_html=old_html))

    assert summary["n_error"] == 1
    assert store.rows[JOBS_TAB][0]["status"] == "error"
    assert "body_xpath not found" in store.rows[JOBS_TAB][0]["error"]
    assert "//*[@id='missing']" in store.rows[JOBS_TAB][0]["error"]


def test_run_jobs_keeps_drive_input_for_non_url(monkeypatch):
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "drive-job",
        "site": "saga-city",
        "page_id": "drive-page",
        "input_file": "custom/input.html",
        "body_xpath": "//*[@id='ignored-for-drive']",
        "status": "queued",
    }]
    drive = InMemoryDriveStore({("input", "custom/input.html"): "<html><body><p>Drive</p></body></html>"})

    def fail_get(*args, **kwargs):
        raise AssertionError("requests.get should not be called for Drive input")

    monkeypatch.setattr("a11y_runner.runner.requests.get", fail_get)

    def fake_engine(old_html, **kwargs):
        return PageResult(ai_html=old_html)

    summary = run_jobs(store, drive, engine=fake_engine)

    assert summary["n_done"] == 1
    assert drive.files[("ai", "saga-city/drive-page.html")] == "<html><body><p>Drive</p></body></html>"


def test_run_jobs_records_error_when_url_fetch_fails(monkeypatch):
    store = _store_with_config()
    store.rows[JOBS_TAB] = [{
        "job_id": "url-job",
        "site": "saga-city",
        "page_id": "url-page",
        "input_file": "https://www.example.jp/missing.html",
        "status": "queued",
    }]

    monkeypatch.setattr(
        "a11y_runner.runner.requests.get",
        lambda *args, **kwargs: _FakeResponse("not found", status_error=RuntimeError("404 Client Error")),
    )

    summary = run_jobs(store, InMemoryDriveStore({}), engine=lambda old_html, **kwargs: PageResult(ai_html=old_html))

    assert summary["n_error"] == 1
    assert store.rows[JOBS_TAB][0]["status"] == "error"
    assert "404 Client Error" in store.rows[JOBS_TAB][0]["error"]


class _FakeResponse:
    def __init__(self, text, *, encoding=None, apparent_encoding="utf-8", status_error=None):
        self._text = text
        self.encoding = encoding
        self.apparent_encoding = apparent_encoding
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error:
            raise self._status_error

    @property
    def text(self):
        return self._text


def _set_config(store, key, value):
    for row in store.rows[CONFIG_TAB]:
        if row["key"] == key:
            row["value"] = value
            return
    store.rows[CONFIG_TAB].append({"key": key, "value": value})
