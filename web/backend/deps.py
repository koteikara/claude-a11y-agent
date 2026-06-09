# -*- coding: utf-8 -*-
"""Dependency helpers for the web admin API.

The web UI intentionally uses the same Sheets and Drive adapters as the
Phase 1 runner. Google Sheets remains the source of truth; this module only
builds clients from environment configuration.
"""

from __future__ import annotations

import os
from functools import lru_cache

from a11y_runner.drive import DriveStore, GoogleDriveStore
from a11y_runner.sheets import GspreadSheetStore, SheetStore


@lru_cache(maxsize=1)
def get_sheet_store() -> SheetStore:
    sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID is required for the web backend")
    return GspreadSheetStore(sheet_id)


@lru_cache(maxsize=1)
def get_drive_store() -> DriveStore:
    return GoogleDriveStore()


def reset_dependency_cache() -> None:
    """Clear cached clients. Tests use this after monkeypatching env vars."""

    get_sheet_store.cache_clear()
    get_drive_store.cache_clear()
