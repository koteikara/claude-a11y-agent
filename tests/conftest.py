# -*- coding: utf-8 -*-
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # mechanical_rules / a11y_testkit を import 可能に

CASES = ROOT / "tests" / "cases"
SPECS = ROOT / "specs"


def _load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture(scope="session")
def mechanical_cases():
    return _load_jsonl(CASES / "mechanical_cases.jsonl")


@pytest.fixture(scope="session")
def prompt_cases():
    return _load_jsonl(CASES / "prompt_cases.jsonl")


@pytest.fixture(scope="session")
def prompt_templates():
    """ルールID -> 修正プロンプト雛形 の辞書（仕様JSONLから読込）。"""
    rows = _load_jsonl(SPECS / "a11y_hybrid_detect_fix.jsonl")
    return {r["id"]: r["修正プロンプト"] for r in rows}


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "llm: 実LLMを呼ぶテスト（既定スキップ。RUN_LLM_TESTS=1 で有効化）"
    )


def pytest_collection_modifyitems(config, items):
    """RUN_LLM_TESTS=1 かつ APIキーが無ければ llm マーカーをスキップ。"""
    run = os.getenv("RUN_LLM_TESTS") == "1"
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    key_env = "GEMINI_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
    has_key = bool(os.getenv(key_env))
    if run and has_key:
        return
    reason = "set RUN_LLM_TESTS=1" if not run else f"missing {key_env}"
    skip = pytest.mark.skip(reason=f"LLMテストはスキップ: {reason}")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip)
