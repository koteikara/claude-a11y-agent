# -*- coding: utf-8 -*-
"""Sheet storage adapters used by the CLI runner.

The production adapter wraps gspread. Unit tests can use InMemorySheetStore to
exercise the runner without Google credentials or network access.
"""

from __future__ import annotations

import importlib.util
import os
from copy import deepcopy
from typing import Protocol

from .schema import TAB_HEADERS

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetStore(Protocol):
    def ensure_tab(self, tab: str, headers: list[str]) -> None: ...
    def get_rows(self, tab: str) -> list[dict]: ...
    def append_rows(self, tab: str, rows: list[dict]) -> None: ...
    def update_row(self, tab: str, row_number: int, values: dict) -> None: ...


class InMemorySheetStore:
    """Small SheetStore implementation for tests and local dry-run examples."""

    def __init__(self, rows: dict[str, list[dict]] | None = None):
        self.headers: dict[str, list[str]] = {}
        self.rows: dict[str, list[dict]] = deepcopy(rows or {})

    def ensure_tab(self, tab: str, headers: list[str]) -> None:
        self.headers.setdefault(tab, list(headers))
        existing = self.headers[tab]
        for header in headers:
            if header not in existing:
                existing.append(header)
        self.rows.setdefault(tab, [])

    def get_rows(self, tab: str) -> list[dict]:
        return [dict(row, _row_number=idx + 2) for idx, row in enumerate(self.rows.get(tab, []))]

    def append_rows(self, tab: str, rows: list[dict]) -> None:
        self.rows.setdefault(tab, []).extend(deepcopy(rows))

    def update_row(self, tab: str, row_number: int, values: dict) -> None:
        index = row_number - 2
        if index < 0 or index >= len(self.rows.get(tab, [])):
            raise IndexError(f"row_number out of range: {tab}!{row_number}")
        clean_values = {k: v for k, v in values.items() if k != "_row_number"}
        self.rows[tab][index].update(clean_values)


class GspreadSheetStore:
    """Google Sheets adapter backed by gspread and Google ADC/service-account auth."""

    def __init__(self, sheet_id: str):
        if importlib.util.find_spec("gspread") is None:  # pragma: no cover - depends on optional package
            raise RuntimeError(
                "gspread is required. Install runner dependencies with "
                "`pip install -r requirements-runner.txt`."
            )
        import gspread
        import google.auth

        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if credentials_path:
            client = gspread.service_account(filename=credentials_path)
        else:
            credentials, _ = google.auth.default(scopes=SHEETS_SCOPES)
            client = gspread.authorize(credentials)
        self._spreadsheet = client.open_by_key(sheet_id)

    def ensure_tab(self, tab: str, headers: list[str]) -> None:
        worksheet = self._worksheet(tab, create=True, cols=max(len(headers), 20))
        current = worksheet.row_values(1)
        if not current:
            worksheet.update("A1", [headers])
            return
        merged = list(current)
        for header in headers:
            if header not in merged:
                merged.append(header)
        if merged != current:
            worksheet.update("A1", [merged])

    def get_rows(self, tab: str) -> list[dict]:
        worksheet = self._worksheet(tab)
        records = worksheet.get_all_records()
        return [dict(row, _row_number=idx + 2) for idx, row in enumerate(records)]

    def append_rows(self, tab: str, rows: list[dict]) -> None:
        if not rows:
            return
        worksheet = self._worksheet(tab)
        headers = worksheet.row_values(1)
        values = [[row.get(header, "") for header in headers] for row in rows]
        worksheet.append_rows(values, value_input_option="USER_ENTERED")

    def update_row(self, tab: str, row_number: int, values: dict) -> None:
        worksheet = self._worksheet(tab)
        headers = worksheet.row_values(1)
        data = [{"range": self._cell(row_number, headers.index(key) + 1), "values": [[value]]}
                for key, value in values.items()
                if key in headers and key != "_row_number"]
        if data:
            worksheet.batch_update(data, value_input_option="USER_ENTERED")

    def _worksheet(self, tab: str, *, create: bool = False, cols: int = 20):
        try:
            return self._spreadsheet.worksheet(tab)
        except Exception:
            if not create:
                raise
            return self._spreadsheet.add_worksheet(title=tab, rows=1000, cols=cols)

    @staticmethod
    def _cell(row: int, col: int) -> str:
        letters = ""
        while col:
            col, rem = divmod(col - 1, 26)
            letters = chr(65 + rem) + letters
        return f"{letters}{row}"


def ensure_schema(store: SheetStore) -> None:
    for tab, headers in TAB_HEADERS.items():
        store.ensure_tab(tab, headers)
