# -*- coding: utf-8 -*-
"""old/ai/gold HTMLペアのデータ駆動回帰テスト。"""

from __future__ import annotations

import importlib
import re
import warnings

import pytest

from conftest import fixture_path, load_body


UNKNOWN_CHECK_MESSAGE = "未知のcheck種別"

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


def _check_no_tag(check, gold_body, old_body):
    tags = [tag.lower() for tag in _as_list(check.get("tag", []))]
    found = [el.tag for el in gold_body.iter() if isinstance(el.tag, str) and el.tag.lower() in tags]
    return not found, f"禁止タグが存在します: {found[:10]}"


def _check_no_anchor_text(check, gold_body, old_body):
    values = _as_list(check.get("value", []))
    violations = []
    for anchor in gold_body.xpath(".//a"):
        text = _collapse_ws("".join(anchor.itertext()))
        for value in values:
            if value in text:
                violations.append(text)
                break
    return not violations, f"指示語リンクが存在します: {violations[:10]}"


def _check_anchor_href_present(check, gold_body, old_body):
    violations = [_collapse_ws("".join(a.itertext())) for a in gold_body.xpath(".//a[not(@href) or normalize-space(@href)='']")]
    return not violations, f"hrefなしのa要素があります: {violations[:10]}"


def _check_href_no_pattern(check, gold_body, old_body):
    pattern = re.compile(check.get("pattern", ""))
    violations = [href for href in gold_body.xpath(".//a/@href") if pattern.search(href)]
    return not violations, f"禁止hrefパターンに一致します: {violations[:10]}"


def _check_no_short_weekday(check, gold_body, old_body):
    text = "".join(gold_body.xpath(".//text()"))
    found = re.findall(r"[（(][月火水木金土日][）)]", text)
    return not found, f"短縮曜日が存在します: {found[:10]}"


def _check_alt_present(check, gold_body, old_body):
    violations = [img for img in gold_body.xpath(".//img[not(@alt)]")]
    return not violations, f"alt属性なしのimgがあります: {len(violations)}件"


def _check_no_id(check, gold_body, old_body):
    denied = set(_as_list(check.get("value", [])))
    violations = [el.get("id") for el in gold_body.xpath(".//*[@id]") if el.get("id") in denied]
    return not violations, f"禁止idが存在します: {violations[:10]}"


def _check_no_layout_table(check, gold_body, old_body):
    violations = []
    for table in gold_body.xpath(".//table[not(.//th)]"):
        classes = set((table.get("class") or "").split())
        if table.get("border") == "0" or classes.intersection({"nb", "layout"}):
            violations.append(table)
    return not violations, f"レイアウトテーブル疑いがあります: {len(violations)}件"


def _check_no_consecutive_br(check, gold_body, old_body):
    html_text = _serialize(gold_body)
    found = re.search(r"<br\b[^>]*>\s*(?:</br>\s*)?<br\b", html_text, flags=re.IGNORECASE)
    return found is None, "連続brが存在します"


def _check_tag_count_not_decreased(check, gold_body, old_body):
    tag = check.get("tag")
    if not tag or check.get("baseline") != "old":
        return False, "tag_count_not_decreasedにはtagとbaseline:'old'が必要です"
    old_count = len(old_body.xpath(f".//{tag}"))
    gold_count = len(gold_body.xpath(f".//{tag}"))
    return gold_count >= old_count, f"{tag}数が減少しました: old={old_count}, gold={gold_count}"


def _check_no_attr(check, gold_body, old_body):
    denied = set(_as_list(check.get("deny", [])))
    violations = []
    for el in gold_body.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in el.attrib:
            if attr in denied:
                violations.append(f"<{el.tag} {attr}>")
    return not violations, f"禁止属性が存在します: {violations[:10]}"


def _check_attr_whitelist(check, gold_body, old_body):
    allow = set(_as_list(check.get("allow", [])))
    violations = []
    for el in gold_body.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in el.attrib:
            if attr not in allow:
                violations.append(f"<{el.tag} {attr}>")
    return not violations, f"許可外属性が存在します: {violations[:10]}"


def _check_text_coverage(check, gold_body, old_body):
    pytest.importorskip("lxml")
    from a11y_testkit.htmlpairs import visible_text_len

    min_ratio = float(check.get("min_ratio", 0.6))
    old_len = visible_text_len(old_body)
    gold_len = visible_text_len(gold_body)
    ratio = 1.0 if old_len == 0 else gold_len / old_len
    return ratio >= min_ratio, f"テキスト被覆率が不足しています: {ratio:.3f} < {min_ratio} (old={old_len}, gold={gold_len})"


def _check_no_sentence_ends_with(check, gold_body, old_body):
    endings = _as_list(check.get("value", []))
    scopes = _as_list(check.get("scope", ["a", "p", "li"]))
    xpath = " | ".join(f".//{scope}" for scope in scopes)
    violations = []
    for el in gold_body.xpath(xpath):
        text = _collapse_ws("".join(el.itertext()))
        if text and any(text.endswith(ending) for ending in endings):
            violations.append(text)
    return not violations, f"未完了文末疑いがあります: {violations[:10]}"


CHECKS = {
    "no_tag": _check_no_tag,
    "no_anchor_text": _check_no_anchor_text,
    "anchor_href_present": _check_anchor_href_present,
    "href_no_pattern": _check_href_no_pattern,
    "no_short_weekday": _check_no_short_weekday,
    "alt_present": _check_alt_present,
    "no_id": _check_no_id,
    "no_layout_table": _check_no_layout_table,
    "no_consecutive_br": _check_no_consecutive_br,
    "tag_count_not_decreased": _check_tag_count_not_decreased,
    "no_attr": _check_no_attr,
    "attr_whitelist": _check_attr_whitelist,
    "text_coverage": _check_text_coverage,
    "no_sentence_ends_with": _check_no_sentence_ends_with,
}


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _collapse_ws(value):
    return re.sub(r"\s+", " ", value).strip()


def _serialize(tree):
    from lxml import etree

    return etree.tostring(tree, encoding="unicode", method="html")
