# -*- coding: utf-8 -*-
"""Google Sheets control-plane schema for the accessibility runner."""

from __future__ import annotations

CONFIG_TAB = "Config"
SITES_TAB = "Sites"
JOBS_TAB = "Jobs"
RUNS_TAB = "Runs"
REVIEW_TAB = "Review"
METRICS_TAB = "Metrics"

CONFIG_HEADERS = ["key", "value"]
SITES_HEADERS = ["site", "body_xpath", "notes"]
JOBS_HEADERS = [
    "job_id",
    "site",
    "page_id",
    "input_file",
    "provider",
    "priority",
    "status",
    "created_at",
    "started_at",
    "finished_at",
    "ai_output_link",
    "gold_output_link",
    "review_status",
    "reviewer",
    "error",
    "notes",
]
RUNS_HEADERS = [
    "run_id",
    "started_at",
    "finished_at",
    "triggered_by",
    "n_total",
    "n_done",
    "n_error",
    "n_review",
    "notes",
]
REVIEW_HEADERS = [
    "job_id",
    "page_id",
    "kind",
    "rule_id",
    "message",
    "location",
    "suggestion",
    "decision",
    "reviewer",
]
METRICS_HEADERS = [
    "job_id",
    "page_id",
    "n_mechanical_fixes",
    "n_llm_fixes",
    "checks_passed",
    "checks_failed",
    "advisory_hits",
]

TAB_HEADERS = {
    CONFIG_TAB: CONFIG_HEADERS,
    SITES_TAB: SITES_HEADERS,
    JOBS_TAB: JOBS_HEADERS,
    RUNS_TAB: RUNS_HEADERS,
    REVIEW_TAB: REVIEW_HEADERS,
    METRICS_TAB: METRICS_HEADERS,
}

DEFAULT_CONFIG = {
    "llm_provider": "gemini",
    "gemini_model": "gemini-1.5-pro",
    "claude_model": "claude-sonnet-4-20250514",
    "drive_input_folder_id": "",
    "drive_output_ai_folder_id": "",
    "drive_output_gold_folder_id": "",
    "run_mode": "batch",
    "default_site": "saga-city",
}
