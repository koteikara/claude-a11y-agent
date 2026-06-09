# -*- coding: utf-8 -*-
import json
import os
import re
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # mechanical_rules / a11y_testkit を import 可能に

CASES = ROOT / "tests" / "cases"
SPECS = ROOT / "specs"
HTML_FIXTURES = ROOT / "tests" / "fixtures" / "html"
HTML_PAIRS = CASES / "html_pairs.jsonl"


def _load_jsonl(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@pytest.fixture(scope="session")
def mechanical_cases():
    return _load_jsonl(CASES / "mechanical_cases.jsonl")


@pytest.fixture(scope="session")
def prompt_cases():
    return _load_jsonl(CASES / "prompt_cases.jsonl")


@pytest.fixture(scope="session")
def html_pairs():
    """old/ai/gold HTMLペア索引をロードする。"""
    return _load_jsonl(HTML_PAIRS)


@pytest.fixture(scope="session")
def prompt_templates():
    """ルールID -> 修正プロンプト雛形 の辞書（仕様JSONLから読込）。"""
    rows = _load_jsonl(SPECS / "a11y_hybrid_detect_fix.jsonl")
    return {r["id"]: r["修正プロンプト"] for r in rows}


def fixture_path(site, stage, page_id):
    """HTML fixtureパスを解決する。

    old/gold は厳密名、ai は ``page_id`` または ``page_id_接尾辞`` の最大名を採用する。
    """

    if stage in {"old", "gold"}:
        return HTML_FIXTURES / site / stage / f"{page_id}.html"
    if stage != "ai":
        raise ValueError(f"未知のstage: {stage}")

    ai_dir = HTML_FIXTURES / site / "ai"
    if not ai_dir.is_dir():
        return None
    pattern = re.compile(rf"^{re.escape(page_id)}(_.*)?\.html$")
    candidates = sorted(path for path in ai_dir.iterdir() if path.is_file() and pattern.match(path.name))
    if not candidates:
        return None
    if len(candidates) > 1:
        warnings.warn(
            f"AI fixture候補が複数あります: {site}/{page_id}: "
            + ", ".join(path.name for path in candidates)
            + f"。{candidates[-1].name} を採用します。",
            stacklevel=2,
        )
    return candidates[-1]


def load_body(path, body_xpath=None):
    """HTMLをlxmlでパースし、body_xpath指定時は該当要素を返す。"""

    pytest.importorskip("lxml")
    from a11y_testkit.htmlpairs import parse_html_document

    source = Path(path).read_text(encoding="utf-8", errors="replace")
    root = parse_html_document(source)
    if not body_xpath:
        return root
    matches = root.xpath(body_xpath)
    if not matches:
        pytest.skip(f"body_xpathに一致する要素がありません: {body_xpath}")
    return matches[0]


def pytest_generate_tests(metafunc):
    if "html_pair" in metafunc.fixturenames:
        pairs = _load_jsonl(HTML_PAIRS)
        if not pairs:
            metafunc.parametrize("html_pair", [None], ids=["html-pairs-empty"])
            return
        metafunc.parametrize("html_pair", pairs, ids=[row.get("id", "html-pair") for row in pairs])


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "llm: 実LLMを呼ぶテスト（既定スキップ。RUN_LLM_TESTS=1 で有効化）"
    )
    config.addinivalue_line("markers", "drift: ai↔goldの情報提供ドリフト比較")
    config.addinivalue_line("markers", "e2e: 実エージェント本体を接続するE2E回帰")


def pytest_collection_modifyitems(config, items):
    """llm/e2e マーカーを環境変数に応じてスキップする。"""

    run_llm = os.getenv("RUN_LLM_TESTS") == "1"
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    key_env = "GEMINI_API_KEY" if provider == "gemini" else "ANTHROPIC_API_KEY"
    has_key = bool(os.getenv(key_env))
    llm_skip = None
    if not (run_llm and has_key):
        reason = "set RUN_LLM_TESTS=1" if not run_llm else f"missing {key_env}"
        llm_skip = pytest.mark.skip(reason=f"LLMテストはスキップ: {reason}")

    html_pairs_skip = None
    if os.getenv("RUN_HTML_PAIRS") != "1":
        html_pairs_skip = pytest.mark.skip(reason="HTMLペア回帰はスキップ: set RUN_HTML_PAIRS=1")

    e2e_skip = None
    if os.getenv("RUN_E2E") != "1":
        e2e_skip = pytest.mark.skip(reason="E2Eテストはスキップ: set RUN_E2E=1")

    for item in items:
        if llm_skip is not None and "llm" in item.keywords:
            item.add_marker(llm_skip)
        if html_pairs_skip is not None and "html_pairs" in item.keywords:
            item.add_marker(html_pairs_skip)
        if e2e_skip is not None and "e2e" in item.keywords:
            item.add_marker(e2e_skip)
