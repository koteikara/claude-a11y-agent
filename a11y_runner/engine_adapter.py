# -*- coding: utf-8 -*-
"""UI-independent engine adapter used by the Sheets/Drive runner.

This adapter is deliberately small: it exposes the required ``process_page``
interface and delegates to existing mechanical rules when their dependencies are
available. It is safe as a fallback when the full agent engine is not present.
"""

from __future__ import annotations

import importlib.util
import os
import re
from copy import deepcopy

from .models import PageResult, ReviewItem

TELFAX_RE = re.compile(r"(TEL|FAX|ＴＥＬ|ＦＡＸ)", re.IGNORECASE)
VAGUE_LINK_RE = re.compile(r"こちら|ここ|詳細")


def process_page(old_html: str, *, site: str, page_id: str, body_xpath: str | None,
                 provider: str, mode: str) -> PageResult:
    """Process a single HTML page and return generated HTML plus review items.

    The full Claude-A11y Agent can replace this function later. The fallback
    implementation applies deterministic DOM cleanups from ``mechanical_rules``
    when lxml is installed, and records low-confidence findings as Review rows.
    """

    os.environ["LLM_PROVIDER"] = provider
    ai_html = old_html
    mechanical_fixes: list[dict] = []
    review_items: list[ReviewItem] = []

    dom_result = _apply_dom_mechanical_rules(old_html)
    if dom_result is not None:
        ai_html, applied = dom_result
        mechanical_fixes.extend(applied)

    if TELFAX_RE.search(old_html):
        review_items.append(ReviewItem(
            kind="mechanical",
            rule_id="TELFAX-R-01",
            message="TEL/FAX表記を検出しました。語中・固有名詞の可能性がないか確認してください。",
            location=_excerpt(old_html, TELFAX_RE),
            suggestion="文脈に応じて電話番号・ファクス番号の表記へ補正してください。",
        ))

    if VAGUE_LINK_RE.search(old_html):
        review_items.append(ReviewItem(
            kind="advisory",
            rule_id="LINK-R-01",
            message="「こちら」「ここ」「詳細」などの指示語リンクを検出しました。リンク先が分かる文言にしてください。",
            location=_excerpt(old_html, VAGUE_LINK_RE),
            suggestion="リンクテキストへリンク先の内容を含めてください。",
        ))

    if mode == "interactive" and mechanical_fixes:
        review_items.append(ReviewItem(
            kind="question",
            rule_id="INTERACTIVE-STOP",
            message="interactive モードのため、機械修正後にレビュー待ちで停止します。",
            location=page_id,
            suggestion="Reviewタブで承認後、次工程を実行してください。",
        ))

    stats = {
        "site": site,
        "page_id": page_id,
        "body_xpath": body_xpath or "",
        "n_mechanical_fixes": len(mechanical_fixes),
        "n_llm_fixes": 0,
        "n_review": len(review_items),
    }
    return PageResult(
        ai_html=ai_html,
        mechanical_fixes=mechanical_fixes,
        llm_fixes=[],
        needs_review=review_items,
        stats=stats,
    )


def _apply_dom_mechanical_rules(old_html: str) -> tuple[str, list[dict]] | None:
    if importlib.util.find_spec("lxml") is None:
        return None
    from lxml import etree
    from a11y_testkit.htmlpairs import parse_html_document
    import mechanical_rules as rules

    tree = parse_html_document(old_html)
    before = etree.tostring(deepcopy(tree), encoding="unicode", method="html")
    applied = []
    for name in ("fix_background_color", "fix_decoration_tags", "fix_font_spec", "normalize_bold"):
        func = getattr(rules, name)
        func(tree)
        applied.append({"rule_id": name, "type": "mechanical"})
    after = etree.tostring(tree, encoding="unicode", method="html")
    if before == after:
        applied = []
    return after, applied


def _excerpt(text: str, pattern: re.Pattern[str], window: int = 150) -> str:
    match = pattern.search(text)
    if not match:
        return text[: window * 2]
    start = max(0, match.start() - window)
    end = min(len(text), match.end() + window)
    return text[start:end].replace("\n", " ")[:300]
