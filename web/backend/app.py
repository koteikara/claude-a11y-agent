# -*- coding: utf-8 -*-
"""FastAPI app for the thin Sheets/Drive-backed accessibility admin UI."""

from __future__ import annotations

import base64
import difflib
import os
import re
import secrets
import uuid
from collections import Counter
from pathlib import Path
from typing import Literal

try:  # imported at module load so deployment fails early if web deps are absent
    import bleach
    from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
    from fastapi.responses import HTMLResponse, Response
    from fastapi.security import HTTPBasic, HTTPBasicCredentials
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel, Field
except ModuleNotFoundError as exc:  # pragma: no cover - dependency installation error path
    raise RuntimeError("Install web dependencies with `pip install -r web/requirements.txt`.") from exc

from a11y_runner import engine_adapter
from a11y_runner.drive import DriveStore
from a11y_runner.runner import _config_dict, _input_path, _run_one_job, _site_config, init_sheet, promote_requested_gold, utc_now
from a11y_runner.schema import CONFIG_TAB, JOBS_TAB, METRICS_TAB, REVIEW_TAB
from a11y_runner.sheets import SheetStore
from a11y_testkit.htmlpairs import element_fingerprints, normalized_html, parse_html_document

from .deps import get_drive_store, get_sheet_store

Stage = Literal["old", "ai", "gold"]
Decision = Literal["accept", "edit", "skip"]

security = HTTPBasic(auto_error=False)
app = FastAPI(title="Claude A11y Admin", version="0.1.0")


def _require_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    if _auth_disabled():
        return
    username = os.getenv("BASIC_AUTH_USERNAME")
    password = os.getenv("BASIC_AUTH_PASSWORD")
    if not username or not password:
        raise HTTPException(status_code=503, detail="Configure IAP/OAuth or BASIC_AUTH_USERNAME/PASSWORD before exposing the API")
    if credentials and secrets.compare_digest(credentials.username, username) and secrets.compare_digest(credentials.password, password):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required", headers={"WWW-Authenticate": "Basic"})


def _auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED_FOR_TESTS", "").lower() in {"1", "true", "yes"}


class JobCreate(BaseModel):
    site: str = Field(..., min_length=1)
    page_id: str = Field(..., min_length=1)
    input_file: str | None = None
    provider: str | None = None
    priority: int | str | None = None
    notes: str | None = None


class ApproveRequest(BaseModel):
    gold_html: str | None = None
    reviewer: str | None = None


class ReviewDecision(BaseModel):
    decision: Decision
    reviewer: str | None = None


@app.middleware("http")
async def require_private_auth(request: Request, call_next):
    # API routes use the FastAPI dependency below. For the SPA shell, require
    # Basic Auth too unless tests explicitly disable auth. Static JS/CSS assets
    # are harmless without data, but Cloud Run + IAP should protect all paths in
    # production.
    if request.url.path == "/healthz":
        return await call_next(request)
    if not request.url.path.startswith("/api/") and not _static_asset(request.url.path) and not _auth_disabled():
        username = os.getenv("BASIC_AUTH_USERNAME")
        password = os.getenv("BASIC_AUTH_PASSWORD")
        if not username or not password:
            return Response("Configure IAP/OAuth or BASIC_AUTH_USERNAME/PASSWORD before exposing the web UI", status_code=503)
        if not _basic_header_matches(request.headers.get("authorization", ""), username, password):
            return Response("Authentication required", status_code=401, headers={"WWW-Authenticate": "Basic"})
    return await call_next(request)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/jobs", dependencies=[Depends(_require_auth)])
def list_jobs(site: str | None = None, status: str | None = None, store: SheetStore = Depends(get_sheet_store)):
    init_sheet(store)
    rows = [_public_row(row) for row in store.get_rows(JOBS_TAB)]
    if site:
        rows = [row for row in rows if row.get("site") == site]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    return {"jobs": rows}


@app.get("/api/jobs/{job_id}", dependencies=[Depends(_require_auth)])
def get_job(job_id: str, store: SheetStore = Depends(get_sheet_store)):
    init_sheet(store)
    job = _find_job(store, job_id)
    return {"job": _with_review_counts(store, _public_row(job))}


@app.post("/api/jobs", status_code=201, dependencies=[Depends(_require_auth)])
def create_job(payload: JobCreate, store: SheetStore = Depends(get_sheet_store)):
    init_sheet(store)
    job_id = uuid.uuid4().hex[:12]
    row = {
        "job_id": job_id,
        "site": payload.site,
        "page_id": payload.page_id,
        "input_file": payload.input_file or "",
        "provider": payload.provider or "",
        "priority": payload.priority or "",
        "status": "queued",
        "created_at": utc_now(),
        "started_at": "",
        "finished_at": "",
        "ai_output_link": "",
        "gold_output_link": "",
        "review_status": "",
        "reviewer": "",
        "promote_requested": "false",
        "error": "",
        "notes": payload.notes or "",
    }
    store.append_rows(JOBS_TAB, [row])
    return {"job": row}


@app.post("/api/jobs/{job_id}/run", dependencies=[Depends(_require_auth)])
def run_job(job_id: str, background: BackgroundTasks, store: SheetStore = Depends(get_sheet_store), drive: DriveStore = Depends(get_drive_store)):
    init_sheet(store)
    job = _find_job(store, job_id)
    if str(job.get("status", "")).strip() == "running":
        raise HTTPException(status_code=409, detail="Job is already running")
    store.update_row(JOBS_TAB, job["_row_number"], {"status": "queued", "error": ""})
    background.add_task(_run_job_task, store, drive, job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}/html", response_class=HTMLResponse, dependencies=[Depends(_require_auth)])
def get_html(job_id: str, stage: Stage = Query(...), store: SheetStore = Depends(get_sheet_store), drive: DriveStore = Depends(get_drive_store)):
    init_sheet(store)
    job = _find_job(store, job_id)
    return HTMLResponse(_sanitize_html(_read_stage_html(store, drive, job, stage)))


@app.get("/api/jobs/{job_id}/diff", dependencies=[Depends(_require_auth)])
def get_diff(job_id: str, store: SheetStore = Depends(get_sheet_store), drive: DriveStore = Depends(get_drive_store)):
    init_sheet(store)
    job = _find_job(store, job_id)
    stages = {}
    for stage in ("old", "ai", "gold"):
        try:
            stages[stage] = _read_stage_html(store, drive, job, stage)  # type: ignore[arg-type]
        except Exception:
            stages[stage] = ""
    return {"job_id": job_id, "old_ai": _diff_pair(stages["old"], stages["ai"]), "ai_gold": _diff_pair(stages["ai"], stages["gold"])}


@app.post("/api/jobs/{job_id}/approve", dependencies=[Depends(_require_auth)])
def approve_job(job_id: str, payload: ApproveRequest | None = None, store: SheetStore = Depends(get_sheet_store), drive: DriveStore = Depends(get_drive_store)):
    init_sheet(store)
    job = _find_job(store, job_id)
    config = _config_dict(store)
    site = job.get("site") or config.get("default_site", "")
    page_id = job.get("page_id", "")
    if not site or not page_id:
        raise HTTPException(status_code=400, detail="site and page_id are required")
    gold_html = (payload.gold_html if payload and payload.gold_html is not None else None)
    if gold_html is None:
        gold_html = _read_stage_html(store, drive, job, "ai")
    gold_link = drive.write_text(config.get("drive_output_gold_folder_id", ""), f"{site}/{page_id}.html", gold_html)
    store.update_row(JOBS_TAB, job["_row_number"], {
        "gold_output_link": gold_link,
        "review_status": "approved",
        "reviewer": (payload.reviewer if payload else "") or job.get("reviewer", ""),
        "promote_requested": "false",
        "error": "",
    })
    promote_requested_gold(store, drive)
    return {"job_id": job_id, "review_status": "approved", "gold_output_link": gold_link}


@app.get("/api/review", dependencies=[Depends(_require_auth)])
def list_review(status: str | None = "open", store: SheetStore = Depends(get_sheet_store)):
    init_sheet(store)
    rows = [_public_row(row) for row in store.get_rows(REVIEW_TAB)]
    if status:
        rows = [row for row in rows if row.get("decision", "open") == status]
    return {"review": rows}


@app.post("/api/review/{review_id}/decision", dependencies=[Depends(_require_auth)])
def decide_review(review_id: int, payload: ReviewDecision, store: SheetStore = Depends(get_sheet_store)):
    init_sheet(store)
    rows = store.get_rows(REVIEW_TAB)
    row = next((r for r in rows if int(r.get("_row_number", -1)) == review_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Review row not found")
    store.update_row(REVIEW_TAB, row["_row_number"], {"decision": payload.decision, "reviewer": payload.reviewer or row.get("reviewer", "")})
    return {"id": review_id, "decision": payload.decision}


@app.get("/api/metrics", dependencies=[Depends(_require_auth)])
def metrics(store: SheetStore = Depends(get_sheet_store)):
    init_sheet(store)
    jobs = store.get_rows(JOBS_TAB)
    reviews = store.get_rows(REVIEW_TAB)
    metrics_rows = store.get_rows(METRICS_TAB)
    return {
        "jobs_by_status": dict(Counter(str(row.get("status") or "unknown") for row in jobs)),
        "review_by_decision": dict(Counter(str(row.get("decision") or "open") for row in reviews)),
        "totals": {
            "jobs": len(jobs),
            "review_open": sum(1 for row in reviews if str(row.get("decision") or "open") == "open"),
            "checks_passed": _sum_int(metrics_rows, "checks_passed"),
            "checks_failed": _sum_int(metrics_rows, "checks_failed"),
            "advisory_hits": _sum_int(metrics_rows, "advisory_hits"),
        },
        "rows": [_public_row(row) for row in metrics_rows],
    }


def _run_job_task(store: SheetStore, drive: DriveStore, job_id: str) -> None:
    try:
        init_sheet(store)
        job = _find_job(store, job_id)
        _run_one_job(store, drive, job, config=_config_dict(store), sites=_site_config(store), engine=engine_adapter.process_page)
    except Exception as exc:
        try:
            job = _find_job(store, job_id)
            store.update_row(JOBS_TAB, job["_row_number"], {"status": "error", "finished_at": utc_now(), "error": f"{type(exc).__name__}: {exc}"})
        except Exception:
            raise



def _basic_header_matches(header: str, username: str, password: str) -> bool:
    if not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except Exception:
        return False
    supplied_user, _, supplied_password = decoded.partition(":")
    return secrets.compare_digest(supplied_user, username) and secrets.compare_digest(supplied_password, password)


def _find_job(store: SheetStore, job_id: str) -> dict:
    for row in store.get_rows(JOBS_TAB):
        if str(row.get("job_id")) == str(job_id):
            return row
    raise HTTPException(status_code=404, detail="Job not found")


def _read_stage_html(store: SheetStore, drive: DriveStore, job: dict, stage: Stage) -> str:
    config = _config_dict(store)
    site = job.get("site") or config.get("default_site", "")
    page_id = job.get("page_id", "")
    if stage == "old":
        return drive.read_text(config.get("drive_input_folder_id", ""), _input_path(job, site, page_id))
    if stage == "ai":
        return drive.read_text(config.get("drive_output_ai_folder_id", ""), f"{site}/{page_id}.html")
    return drive.read_text(config.get("drive_output_gold_folder_id", ""), f"{site}/{page_id}.html")


def _sanitize_html(source: str) -> str:
    allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS).union({
        "html", "head", "body", "main", "section", "article", "header", "footer", "nav", "div", "span", "p", "br",
        "h1", "h2", "h3", "h4", "h5", "h6", "table", "caption", "thead", "tbody", "tfoot", "tr", "th", "td",
        "ul", "ol", "li", "dl", "dt", "dd", "img", "figure", "figcaption", "strong", "em", "b", "i", "u",
    })
    allowed_attrs = {
        "*": ["lang", "title", "colspan", "rowspan", "scope", "summary"],
        "a": ["href", "title", "lang"],
        "img": ["src", "alt", "title", "lang"],
        "th": ["scope", "colspan", "rowspan", "abbr", "headers"],
        "td": ["colspan", "rowspan", "headers"],
        "table": ["summary"],
    }
    return bleach.clean(source, tags=allowed_tags, attributes=allowed_attrs, protocols=["http", "https", "mailto", "tel", "#"], strip=True, strip_comments=True)


def _diff_pair(left_html: str, right_html: str) -> dict:
    if not left_html or not right_html:
        return {"summary": {"added": 0, "removed": 0, "changed": 0}, "items": []}
    left = parse_html_document(left_html)
    right = parse_html_document(right_html)
    left_items = element_fingerprints(left, strip_cms=True)
    right_items = element_fingerprints(right, strip_cms=True)
    left_counts = Counter(left_items)
    right_counts = Counter(right_items)
    removed = list((left_counts - right_counts).elements())
    added = list((right_counts - left_counts).elements())
    norm_left = normalized_html(left, strip_cms=True).splitlines()
    norm_right = normalized_html(right, strip_cms=True).splitlines()
    changed = [line for line in difflib.unified_diff(norm_left, norm_right, n=1) if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    items = ([{"type": "removed", "excerpt": _clean_excerpt(x)} for x in removed[:30]] +
             [{"type": "added", "excerpt": _clean_excerpt(x)} for x in added[:30]] +
             [{"type": "changed", "excerpt": _clean_excerpt(x)} for x in changed[:30]])
    return {"summary": {"added": len(added), "removed": len(removed), "changed": len(changed)}, "items": items[:60]}


def _clean_excerpt(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()[:300]


def _public_row(row: dict) -> dict:
    return {key: value for key, value in row.items() if key != "_row_number"} | ({"id": row["_row_number"]} if "_row_number" in row else {})


def _with_review_counts(store: SheetStore, job: dict) -> dict:
    rows = [row for row in store.get_rows(REVIEW_TAB) if str(row.get("job_id")) == str(job.get("job_id"))]
    job["review_open_count"] = sum(1 for row in rows if str(row.get("decision") or "open") == "open")
    job["review_count"] = len(rows)
    return job


def _sum_int(rows: list[dict], key: str) -> int:
    total = 0
    for row in rows:
        try:
            total += int(row.get(key) or 0)
        except (TypeError, ValueError):
            pass
    return total


def _static_asset(path: str) -> bool:
    return bool(Path(path).suffix)


_frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
