# -*- coding: utf-8 -*-
"""機械処理（文字列入出力）32関数の回帰テスト。
事例は tests/cases/mechanical_cases.jsonl から読み込みデータ駆動で実行。
本番では同形式に変換した24事例Excelを追記する。
"""
import json
from pathlib import Path

import pytest

import mechanical_rules as M

CASES = Path(__file__).resolve().parent / "cases" / "mechanical_cases.jsonl"
ALL = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]

EQUALS = [c for c in ALL if c["kind"] == "equals"]
TELFAX = [c for c in ALL if c["kind"] == "telfax"]
BOOLS = [c for c in ALL if c["kind"] == "bool"]


def _id(c):
    return c["id"]


@pytest.mark.parametrize("c", EQUALS, ids=_id)
def test_equals(c):
    func = getattr(M, c["func"])
    if c.get("xfail"):
        pytest.xfail(c.get("note", "既知の限界"))
    assert func(c["input"]) == c["expected"]


@pytest.mark.parametrize("c", TELFAX, ids=_id)
def test_telfax(c):
    fixed, needs_review = M.fix_telfax(c["input"])
    assert fixed == c["expected_text"]
    assert needs_review is c["expected_review"]


@pytest.mark.parametrize("c", BOOLS, ids=_id)
def test_bool(c):
    func = getattr(M, c["func"])
    if c.get("single_arg"):
        result = func(c["anchor"])
    else:
        result = func(c["href"], c["anchor"])
    assert result is c["expected"]


def test_strip_file_meta_fullwidth_notation():
    assert M.strip_file_meta("申請書（ＰＤＦ：３００ＫＢ）") == "申請書"


def test_relative_file_link_is_internal_file():
    assert M.is_internal_url("/files/report.pdf", {"city.example.lg.jp"}, {}) is True
    assert M.is_external_file_link("/files/report.pdf", {"city.example.lg.jp"}) is False


def test_non_http_file_link_is_not_internal_file():
    assert M.is_internal_url("ftp://example.com/report.pdf", {"example.com"}, {}) is False
    assert M.is_external_file_link("ftp://example.com/report.pdf", {"example.com"}) is True
