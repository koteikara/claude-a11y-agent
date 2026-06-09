# -*- coding: utf-8 -*-
"""sg04009 の old→gold 近似度を標準ライブラリだけで再採点する補助スクリプト。"""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE_ID = "sg04009"
SITE = "saga-city"
OLD_PATH = ROOT / "tests" / "fixtures" / "html" / SITE / "old" / f"{PAGE_ID}.html"
GOLD_PATH = ROOT / "tests" / "fixtures" / "html" / SITE / "gold" / f"{PAGE_ID}.html"
CASE_PATH = ROOT / "tests" / "cases" / "html_pairs.jsonl"
CMS_STRIP = set(
    "class style id role tabindex target width height border cellpadding cellspacing "
    "allow allowfullscreen frameborder referrerpolicy scrolling".split()
)
CMS_PREFIX = ("aria-", "data-")


def collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def stripped_attrs(attrs: dict[str, str]) -> tuple[tuple[str, str], ...]:
    result = []
    for key, value in attrs.items():
        lowered = key.lower()
        if lowered in CMS_STRIP or lowered.startswith(CMS_PREFIX):
            continue
        result.append((lowered, collapse(value or "")))
    return tuple(sorted(result))


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, dict[str, str]]] = []
        self.text: list[str] = []
        self.anchors: list[dict[str, object]] = []
        self.tables: list[dict[str, object]] = []
        self.fingerprints: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        self.in_skip = 0
        self._anchor_stack: list[dict[str, object]] = []
        self._table_stack: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        self.tags.append(tag)
        self.attrs.append((tag, attr_map))
        self.fingerprints.append((tag, stripped_attrs(attr_map)))
        if tag in {"script", "style"}:
            self.in_skip += 1
        if tag == "a":
            self._anchor_stack.append({"attrs": attr_map, "text": []})
        if tag == "table":
            self.tables.append({"attrs": attr_map, "has_th": False})
            self._table_stack.append(len(self.tables) - 1)
        if tag == "th" and self._table_stack:
            self.tables[self._table_stack[-1]]["has_th"] = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"} and self.in_skip:
            self.in_skip -= 1
        if tag == "a" and self._anchor_stack:
            self.anchors.append(self._anchor_stack.pop())
        if tag == "table" and self._table_stack:
            self._table_stack.pop()

    def handle_data(self, data: str) -> None:
        if self.in_skip:
            return
        self.text.append(data)
        if self._anchor_stack:
            text = self._anchor_stack[-1]["text"]
            assert isinstance(text, list)
            text.append(data)


def parse(path: Path) -> Parser:
    parser = Parser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.close()
    return parser


def page_case() -> dict[str, object]:
    for line in CASE_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["page_id"] == PAGE_ID:
            return row
    raise SystemExit(f"case not found: {PAGE_ID}")


def jaccard_counter(left: list[object], right: list[object]) -> float:
    left_counter = Counter(left)
    right_counter = Counter(right)
    intersection = sum((left_counter & right_counter).values())
    union = sum((left_counter | right_counter).values())
    return 1.0 if union == 0 else intersection / union


def check_results(candidate: Parser, baseline_old: Parser, raw_html: str, checks: list[dict[str, object]]):
    results = []
    for check in checks:
        if check.get("advisory"):
            continue
        check_type = str(check["type"])
        ok = True
        violations = 0
        if check_type == "no_tag":
            denied_values = check.get("tag", [])
            denied = set(x.lower() for x in (denied_values if isinstance(denied_values, list) else [denied_values]))
            bad = [tag for tag in candidate.tags if tag in denied]
            ok, violations = not bad, len(bad)
        elif check_type == "no_anchor_text":
            values = check.get("value", [])
            values = values if isinstance(values, list) else [values]
            bad = [
                anchor
                for anchor in candidate.anchors
                if any(value in collapse("".join(anchor["text"])) for value in values)
            ]
            ok, violations = not bad, len(bad)
        elif check_type == "anchor_href_present":
            bad = [anchor for anchor in candidate.anchors if not collapse(anchor["attrs"].get("href", ""))]
            ok, violations = not bad, len(bad)
        elif check_type == "href_no_pattern":
            pattern = re.compile(str(check.get("pattern", "")))
            bad = [attrs.get("href", "") for tag, attrs in candidate.attrs if tag == "a" and pattern.search(attrs.get("href", ""))]
            ok, violations = not bad, len(bad)
        elif check_type == "no_short_weekday":
            bad = re.findall(r"[（(][月火水木金土日][）)]", "".join(candidate.text))
            ok, violations = not bad, len(bad)
        elif check_type == "alt_present":
            bad = [attrs for tag, attrs in candidate.attrs if tag == "img" and "alt" not in attrs]
            ok, violations = not bad, len(bad)
        elif check_type == "no_id":
            denied = set(check.get("value", []))
            bad = [attrs.get("id") for tag, attrs in candidate.attrs if attrs.get("id") in denied]
            ok, violations = not bad, len(bad)
        elif check_type == "no_layout_table":
            bad = [
                table
                for table in candidate.tables
                if not table["has_th"]
                and (table["attrs"].get("border") == "0" or {"nb", "layout"} & set(table["attrs"].get("class", "").split()))
            ]
            ok, violations = not bad, len(bad)
        elif check_type == "no_consecutive_br":
            bad = re.findall(r"<br\b[^>]*>\s*(?:</br>\s*)?<br\b", raw_html, flags=re.I)
            ok, violations = not bad, len(bad)
        elif check_type == "tag_count_not_decreased":
            tag = str(check.get("tag", "")).lower()
            ok = candidate.tags.count(tag) >= baseline_old.tags.count(tag)
            violations = max(0, baseline_old.tags.count(tag) - candidate.tags.count(tag))
        results.append((check_type, ok, violations))
    return results


def main() -> None:
    old = parse(OLD_PATH)
    gold = parse(GOLD_PATH)
    raw = OLD_PATH.read_text(encoding="utf-8", errors="replace")
    checks = check_results(old, old, raw, page_case()["checks"])
    hard_pass = sum(1 for _, ok, _ in checks if ok)
    hard_total = len(checks)
    hard_score = hard_pass / hard_total if hard_total else 1.0
    element_similarity = jaccard_counter(old.fingerprints, gold.fingerprints)
    old_text = collapse("".join(old.text))
    gold_text = collapse("".join(gold.text))
    text_similarity = SequenceMatcher(None, old_text, gold_text).ratio()
    score = 100 * (0.45 * hard_score + 0.25 * element_similarity + 0.30 * text_similarity)
    print(f"page_id={PAGE_ID}")
    print(f"old_bytes={OLD_PATH.stat().st_size}")
    print(f"gold_bytes={GOLD_PATH.stat().st_size}")
    print(f"old_elements={len(old.fingerprints)}")
    print(f"gold_elements={len(gold.fingerprints)}")
    print(f"old_text_len={len(old_text)}")
    print(f"gold_text_len={len(gold_text)}")
    print(f"hard={hard_pass}/{hard_total} ({hard_score * 100:.1f}%)")
    print(f"element_similarity={element_similarity * 100:.1f}%")
    print(f"text_similarity={text_similarity * 100:.1f}%")
    print(f"score={score:.1f}")
    print("checks:")
    for check_type, ok, violations in checks:
        suffix = "" if ok else f" violations={violations}"
        print(f"- {check_type}: {'PASS' if ok else 'FAIL'}{suffix}")


if __name__ == "__main__":
    main()
