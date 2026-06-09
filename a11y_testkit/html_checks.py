# -*- coding: utf-8 -*-
"""Reusable HTML pair checks shared by pytest and the Sheets runner."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

UNKNOWN_CHECK_MESSAGE = "未知のcheck種別"


@dataclass
class CheckResult:
    check_type: str
    ok: bool
    message: str
    advisory: bool = False
    skipped: bool = False


def evaluate_checks(old_html: str, gold_html: str, checks: list[dict], *, body_xpath: str | None = None) -> list[CheckResult]:
    from a11y_testkit.htmlpairs import parse_html_document

    old_body = _select_body(parse_html_document(old_html), body_xpath)
    gold_body = _select_body(parse_html_document(gold_html), body_xpath)
    return [run_check(check, gold_body, old_body) for check in checks]


def run_check(check: dict, gold_body: Any, old_body: Any) -> CheckResult:
    check_type = check.get("type", "")
    evaluator = CHECKS.get(check_type)
    advisory = bool(check.get("advisory", False))
    if evaluator is None:
        return CheckResult(check_type, True, f"{UNKNOWN_CHECK_MESSAGE}: {check_type}", advisory=advisory, skipped=True)
    ok, message = evaluator(check, gold_body, old_body)
    return CheckResult(check_type, ok, message, advisory=advisory)


def _select_body(root: Any, body_xpath: str | None):
    if not body_xpath:
        return root
    matches = root.xpath(body_xpath)
    if not matches:
        raise ValueError(f"body_xpathに一致する要素がありません: {body_xpath}")
    return matches[0]


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
