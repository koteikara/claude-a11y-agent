# -*- coding: utf-8 -*-
"""old/ai/gold HTMLペアのデータ駆動回帰テスト。"""

from __future__ import annotations

import importlib
import warnings

import pytest

from conftest import fixture_path, load_body
from a11y_testkit.html_checks import CHECKS, UNKNOWN_CHECK_MESSAGE

pytestmark = pytest.mark.html_pairs


def _required_fixture_paths(pair):
    if pair is None:
        pytest.skip("HTMLペア索引が空です")
    old_path = fixture_path(pair["site"], "old", pair["page_id"])
    gold_path = fixture_path(pair["site"], "gold", pair["page_id"])
    if old_path is None or gold_path is None or not old_path.exists() or not gold_path.exists():
        pytest.skip(f"fixture未配置: {pair['id']}")
    return old_path, gold_path


def _load_required_bodies(pair):
    old_path, gold_path = _required_fixture_paths(pair)
    body_xpath = pair.get("body_xpath")
    return load_body(old_path, body_xpath), load_body(gold_path, body_xpath)


def test_gold_checks(html_pair):
    """gold本文にチェックセットを適用する。advisoryは警告のみ。"""

    old_body, gold_body = _load_required_bodies(html_pair)
    for check in html_pair.get("checks", []):
        _run_check(check, gold_body, old_body, html_pair["id"])


@pytest.mark.drift
def test_ai_gold_drift(html_pair):
    """ai↔goldの正規化差分を情報出力する（差分があっても失敗しない）。"""

    if not html_pair.get("has_ai", False):
        pytest.skip(f"AI fixtureなし: {html_pair['id']}")
    _, gold_path = _required_fixture_paths(html_pair)
    ai_path = fixture_path(html_pair["site"], "ai", html_pair["page_id"])
    if ai_path is None or not ai_path.exists():
        pytest.skip(f"AI fixture未配置: {html_pair['id']}")

    body_xpath = html_pair.get("body_xpath")
    pytest.importorskip("lxml")
    from a11y_testkit.htmlpairs import drift_element_diff_count, normalized_html

    ai_body = load_body(ai_path, body_xpath)
    gold_body = load_body(gold_path, body_xpath)
    ai_normalized = normalized_html(ai_body)
    gold_normalized = normalized_html(gold_body)
    if ai_normalized != gold_normalized:
        diff_count = drift_element_diff_count(ai_body, gold_body)
        warnings.warn(f"[drift] {html_pair['id']}: ai↔gold 差分要素数={diff_count}", stacklevel=2)


@pytest.mark.e2e
def test_e2e_pipeline(html_pair):
    """将来の pipeline(old) → gold 比較用スケルトン。"""

    old_path, _ = _required_fixture_paths(html_pair)
    pipeline = _import_pipeline_or_skip()

    # 将来実装の流れ:
    # 1. old_path のHTMLを pipeline に渡して変換結果を得る。
    # 2. 変換結果と gold を strip_cms_attrs 適用後に正規化比較する。
    # 3. 差分は許容しつつ、goldチェック相当のhard判定を変換結果にも併用する。
    result = pipeline(old_path)  # pragma: no cover - 本体接続時のみ到達
    assert result is not None


def _import_pipeline_or_skip():
    candidates = (
        "claude_a11y_agent.pipeline",
        "claude_a11y_agent",
        "pipeline",
    )
    for module_name in candidates:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        pipeline = getattr(module, "pipeline", None)
        if callable(pipeline):
            return pipeline
    pytest.skip("エージェント本体 pipeline を import できません")


def _run_check(check, gold_body, old_body, pair_id):
    check_type = check.get("type")
    evaluator = CHECKS.get(check_type)
    if evaluator is None:
        warnings.warn(f"{UNKNOWN_CHECK_MESSAGE}: {check_type} ({pair_id})", stacklevel=2)
        pytest.skip(f"{UNKNOWN_CHECK_MESSAGE}: {check_type}")

    ok, message = evaluator(check, gold_body, old_body)
    if check.get("advisory", False):
        if not ok:
            warnings.warn(f"advisory check failed: {pair_id}: {message}", stacklevel=2)
        return
    assert ok, f"{pair_id}: {message}"
