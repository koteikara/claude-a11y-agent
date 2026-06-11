# -*- coding: utf-8 -*-

from __future__ import annotations

from a11y_runner import cli


def test_cli_uses_env_sheet_id_for_dry_run(monkeypatch, capsys):
    calls = {}

    class FakeSheets:
        def __init__(self, sheet_id: str):
            calls["sheet_id"] = sheet_id

    monkeypatch.setenv("A11Y_SHEET_ID", "sheet-from-env")
    monkeypatch.setattr(cli, "GspreadSheetStore", FakeSheets)
    monkeypatch.setattr(cli, "dry_run", lambda sheets, site=None, limit=None: [{"site": site, "limit": limit}])

    assert cli.main(["run", "--site", "saga-city", "--limit", "3", "--dry-run"]) == 0

    assert calls["sheet_id"] == "sheet-from-env"
    assert '"site": "saga-city"' in capsys.readouterr().out


def test_cli_requires_sheet_id_when_env_is_unset(monkeypatch):
    for name in ("A11Y_SHEET_ID", "GOOGLE_SHEET_ID", "SHEET_ID"):
        monkeypatch.delenv(name, raising=False)

    try:
        cli.main(["run", "--dry-run"])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("main() should exit when no sheet id is configured")
