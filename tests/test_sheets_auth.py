# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib.util
import sys
import types

from a11y_runner.sheets import GspreadSheetStore, SHEETS_SCOPES


def test_gspread_store_uses_adc_when_credentials_path_is_unset(monkeypatch):
    calls = {}

    class FakeClient:
        def open_by_key(self, sheet_id):
            calls["sheet_id"] = sheet_id
            return object()

    def authorize(credentials):
        calls["authorized_credentials"] = credentials
        return FakeClient()

    def default(scopes):
        calls["scopes"] = scopes
        return "adc-creds", "project-id"

    fake_gspread = types.SimpleNamespace(authorize=authorize)
    fake_google_auth = types.SimpleNamespace(default=default)
    fake_google = types.SimpleNamespace(auth=fake_google_auth)

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name):
        if name == "gspread":
            return object()
        return original_find_spec(name)

    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setitem(sys.modules, "gspread", fake_gspread)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.auth", fake_google_auth)
    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    GspreadSheetStore("sheet-123")

    assert calls["scopes"] == SHEETS_SCOPES
    assert calls["authorized_credentials"] == "adc-creds"
    assert calls["sheet_id"] == "sheet-123"


def test_gspread_store_keeps_json_key_path_support(monkeypatch):
    calls = {}

    class FakeClient:
        def open_by_key(self, sheet_id):
            calls["sheet_id"] = sheet_id
            return object()

    def service_account(filename=None):
        calls["filename"] = filename
        return FakeClient()

    fake_gspread = types.SimpleNamespace(service_account=service_account)

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name):
        if name == "gspread":
            return object()
        return original_find_spec(name)

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/secure/key.json")
    monkeypatch.setitem(sys.modules, "gspread", fake_gspread)
    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    GspreadSheetStore("sheet-456")

    assert calls["filename"] == "/secure/key.json"
    assert calls["sheet_id"] == "sheet-456"
