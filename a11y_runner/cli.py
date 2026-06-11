# -*- coding: utf-8 -*-
"""Command line interface for the Sheets/Drive accessibility runner."""

from __future__ import annotations

import argparse
import json
import os

from .drive import GoogleDriveStore
from .runner import check_gold, dry_run, init_sheet, promote_requested_gold, run_jobs
from .sheets import GspreadSheetStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m a11y_runner")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init-sheet", help="タブ/ヘッダを作成・検証します")
    init_parser.add_argument("--sheet", help="Google Sheets ID (defaults to A11Y_SHEET_ID, GOOGLE_SHEET_ID, or SHEET_ID)")

    run_parser = sub.add_parser("run", help="queued ジョブを処理します")
    run_parser.add_argument("--sheet", help="Google Sheets ID (defaults to A11Y_SHEET_ID, GOOGLE_SHEET_ID, or SHEET_ID)")
    run_parser.add_argument("--site", help="対象 site で絞り込み")
    run_parser.add_argument("--limit", type=int, help="処理件数上限")
    run_parser.add_argument("--dry-run", action="store_true", help="対象一覧の表示のみ")

    check_parser = sub.add_parser("check", help="gold HTML に html_pairs チェックを実行します")
    check_parser.add_argument("--sheet", help="Google Sheets ID (defaults to A11Y_SHEET_ID, GOOGLE_SHEET_ID, or SHEET_ID)")
    check_parser.add_argument("--site", help="対象 site で絞り込み")
    check_parser.add_argument("--pairs", default="tests/cases/html_pairs.jsonl", help="html_pairs JSONL パス")

    promote_parser = sub.add_parser("promote", help="approved かつ promote_requested の ai HTML を gold にコピーします")
    promote_parser.add_argument("--sheet", help="Google Sheets ID (defaults to A11Y_SHEET_ID, GOOGLE_SHEET_ID, or SHEET_ID)")

    args = parser.parse_args(argv)
    sheet_id = args.sheet or _env_sheet_id()
    if not sheet_id:
        parser.error("--sheet is required unless A11Y_SHEET_ID, GOOGLE_SHEET_ID, or SHEET_ID is set")
    sheets = GspreadSheetStore(sheet_id)

    if args.command == "init-sheet":
        init_sheet(sheets)
        print("initialized")
        return 0

    if args.command == "run" and args.dry_run:
        rows = dry_run(sheets, site=args.site, limit=args.limit)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        return 0

    drive = GoogleDriveStore()
    if args.command == "run":
        print(json.dumps(run_jobs(sheets, drive, site=args.site, limit=args.limit), ensure_ascii=False, indent=2))
        return 0
    if args.command == "check":
        print(json.dumps(check_gold(sheets, drive, site=args.site, pairs_path=args.pairs), ensure_ascii=False, indent=2))
        return 0
    if args.command == "promote":
        print(json.dumps({"n_promoted": promote_requested_gold(sheets, drive)}, ensure_ascii=False, indent=2))
        return 0
    return 2


def _env_sheet_id() -> str | None:
    return os.getenv("A11Y_SHEET_ID") or os.getenv("GOOGLE_SHEET_ID") or os.getenv("SHEET_ID")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
