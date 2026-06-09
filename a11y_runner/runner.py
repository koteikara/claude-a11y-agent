# -*- coding: utf-8 -*-
"""Core orchestration for the Sheets/Drive accessibility runner."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .drive import DriveStore
from .models import PageResult
from .schema import (
    CONFIG_TAB,
    DEFAULT_CONFIG,
    JOBS_TAB,
    METRICS_TAB,
    REVIEW_TAB,
    RUNS_TAB,
    SITES_TAB,
)
from .sheets import SheetStore, ensure_schema
from . import engine_adapter

EngineFn = Callable[..., PageResult]


class RunnerError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_sheet(store: SheetStore) -> None:
    """Create required tabs/headers and seed default Config rows idempotently."""

    ensure_schema(store)
    config = _config_dict(store)
    missing = [{"key": key, "value": value} for key, value in DEFAULT_CONFIG.items() if key not in config]
    if missing:
        store.append_rows(CONFIG_TAB, missing)
    if not store.get_rows(SITES_TAB):
        store.append_rows(SITES_TAB, [{"site": DEFAULT_CONFIG["default_site"], "body_xpath": "", "notes": ""}])


def queued_jobs(store: SheetStore, *, site: str | None = None, limit: int | None = None) -> list[dict]:
    jobs = [row for row in store.get_rows(JOBS_TAB) if str(row.get("status", "")).strip() == "queued"]
    if site:
        jobs = [row for row in jobs if row.get("site") == site]
    jobs.sort(key=lambda row: (_priority(row), row.get("created_at", ""), row.get("job_id", "")))
    if limit is not None:
        jobs = jobs[:limit]
    return jobs


def dry_run(store: SheetStore, *, site: str | None = None, limit: int | None = None) -> list[dict]:
    init_sheet(store)
    return queued_jobs(store, site=site, limit=limit)


def run_jobs(store: SheetStore, drive: DriveStore, *, site: str | None = None, limit: int | None = None,
             dry_run_only: bool = False, triggered_by: str = "manual",
             engine: EngineFn = engine_adapter.process_page) -> dict:
    """Process queued Jobs rows and update Jobs/Review/Metrics/Runs."""

    init_sheet(store)
    jobs = queued_jobs(store, site=site, limit=limit)
    if dry_run_only:
        return {"jobs": jobs, "n_total": len(jobs), "dry_run": True}

    run_id = uuid.uuid4().hex[:12]
    started_at = utc_now()
    summary = {"run_id": run_id, "n_total": len(jobs), "n_done": 0, "n_error": 0, "n_review": 0}

    config = _config_dict(store)
    sites = _site_config(store)
    for job in jobs:
        try:
            _run_one_job(store, drive, job, config=config, sites=sites, engine=engine)
            updated = _row_by_number(store, JOBS_TAB, job["_row_number"])
            if updated.get("status") == "needs_review":
                summary["n_review"] += 1
            elif updated.get("status") == "done":
                summary["n_done"] += 1
        except Exception as exc:  # keep batch alive and leave a trace per job
            summary["n_error"] += 1
            store.update_row(JOBS_TAB, job["_row_number"], {
                "status": "error",
                "finished_at": utc_now(),
                "error": f"{type(exc).__name__}: {exc}",
            })

    store.append_rows(RUNS_TAB, [{
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": utc_now(),
        "triggered_by": triggered_by,
        "n_total": summary["n_total"],
        "n_done": summary["n_done"],
        "n_error": summary["n_error"],
        "n_review": summary["n_review"],
        "notes": "",
    }])
    return summary


def check_gold(store: SheetStore, drive: DriveStore, *, site: str | None = None,
               pairs_path: str | Path = "tests/cases/html_pairs.jsonl") -> dict:
    """Run existing html_pairs checks against gold files in Drive.

    Results are written to Metrics. Failed hard checks and advisory hits are
    written to Review so non-engineers can triage them in Sheets.
    """

    from a11y_testkit.html_checks import evaluate_checks

    init_sheet(store)
    config = _config_dict(store)
    pairs = _load_pairs(Path(pairs_path))
    pair_by_key = {(row["site"], row["page_id"]): row for row in pairs}
    jobs = [row for row in store.get_rows(JOBS_TAB) if row.get("status") in {"done", "needs_review"}]
    if site:
        jobs = [row for row in jobs if row.get("site") == site]

    summary = {"n_total": 0, "checks_passed": 0, "checks_failed": 0, "advisory_hits": 0}
    for job in jobs:
        pair = pair_by_key.get((job.get("site"), job.get("page_id")))
        if not pair:
            continue
        summary["n_total"] += 1
        page_id = job["page_id"]
        site_name = job["site"]
        old_html = drive.read_text(config.get("drive_input_folder_id", ""), _input_path(job, site_name, page_id))
        gold_html = drive.read_text(config.get("drive_output_gold_folder_id", ""), f"{site_name}/{page_id}.html")
        results = evaluate_checks(old_html, gold_html, pair.get("checks", []), body_xpath=pair.get("body_xpath"))
        passed = sum(1 for result in results if result.ok and not result.skipped)
        failed_results = [result for result in results if not result.ok and not result.advisory]
        advisory_results = [result for result in results if not result.ok and result.advisory]
        summary["checks_passed"] += passed
        summary["checks_failed"] += len(failed_results)
        summary["advisory_hits"] += len(advisory_results)
        store.append_rows(METRICS_TAB, [{
            "job_id": job.get("job_id", ""),
            "page_id": page_id,
            "n_mechanical_fixes": "",
            "n_llm_fixes": "",
            "checks_passed": passed,
            "checks_failed": len(failed_results),
            "advisory_hits": len(advisory_results),
        }])
        review_rows = []
        for result in failed_results + advisory_results:
            review_rows.append({
                "job_id": job.get("job_id", ""),
                "page_id": page_id,
                "kind": "advisory" if result.advisory else "mechanical",
                "rule_id": result.check_type,
                "message": result.message,
                "location": "gold",
                "suggestion": "gold HTMLを確認し、必要に応じて修正してください。",
                "decision": "open",
                "reviewer": "",
            })
        if review_rows:
            store.append_rows(REVIEW_TAB, review_rows)
    return summary


def _run_one_job(store: SheetStore, drive: DriveStore, job: dict, *, config: dict, sites: dict,
                 engine: EngineFn) -> None:
    row_number = job["_row_number"]
    job_id = job.get("job_id") or uuid.uuid4().hex[:12]
    site = job.get("site") or config.get("default_site", "")
    page_id = job.get("page_id", "")
    if not site or not page_id:
        raise RunnerError("site and page_id are required")

    store.update_row(JOBS_TAB, row_number, {
        "job_id": job_id,
        "site": site,
        "status": "running",
        "started_at": utc_now(),
        "error": "",
    })

    provider = job.get("provider") or config.get("llm_provider", "gemini")
    mode = config.get("run_mode", "batch") or "batch"
    body_xpath = sites.get(site, {}).get("body_xpath", "") or None
    old_html = drive.read_text(config.get("drive_input_folder_id", ""), _input_path(job, site, page_id))
    result = engine(old_html, site=site, page_id=page_id, body_xpath=body_xpath, provider=provider, mode=mode)
    ai_path = f"{site}/{page_id}.html"
    ai_link = drive.write_text(config.get("drive_output_ai_folder_id", ""), ai_path, result.ai_html)

    if result.needs_review:
        store.append_rows(REVIEW_TAB, [_review_row(job_id, page_id, item) for item in result.needs_review])
    store.append_rows(METRICS_TAB, [{
        "job_id": job_id,
        "page_id": page_id,
        "n_mechanical_fixes": len(result.mechanical_fixes),
        "n_llm_fixes": len(result.llm_fixes),
        "checks_passed": "",
        "checks_failed": "",
        "advisory_hits": len(result.needs_review),
    }])
    store.update_row(JOBS_TAB, row_number, {
        "status": "needs_review" if result.needs_review else "done",
        "finished_at": utc_now(),
        "ai_output_link": ai_link,
        "review_status": "pending" if result.needs_review else job.get("review_status", ""),
        "error": "",
    })


def _review_row(job_id: str, page_id: str, item) -> dict:
    return {
        "job_id": job_id,
        "page_id": page_id,
        "kind": item.kind,
        "rule_id": item.rule_id,
        "message": item.message,
        "location": item.location,
        "suggestion": item.suggestion or "",
        "decision": "open",
        "reviewer": "",
    }


def _config_dict(store: SheetStore) -> dict:
    return {row.get("key", ""): row.get("value", "") for row in store.get_rows(CONFIG_TAB) if row.get("key")}


def _site_config(store: SheetStore) -> dict:
    return {row.get("site", ""): row for row in store.get_rows(SITES_TAB) if row.get("site")}


def _priority(row: dict) -> tuple[int, str]:
    value = row.get("priority", "")
    try:
        return int(value), str(value)
    except (TypeError, ValueError):
        return 999999, str(value)


def _input_path(job: dict, site: str, page_id: str) -> str:
    value = str(job.get("input_file") or "").strip()
    return value or f"{site}/{page_id}.html"


def _row_by_number(store: SheetStore, tab: str, row_number: int) -> dict:
    for row in store.get_rows(tab):
        if row.get("_row_number") == row_number:
            return row
    return {}


def _load_pairs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
