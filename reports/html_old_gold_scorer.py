# -*- coding: utf-8 -*-
"""old HTML と gold HTML の近似度を全ページ分採点し、レポートを保存する。"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CASE_PATH = ROOT / "tests" / "cases" / "html_pairs.jsonl"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "html"
REPORT_PATH = ROOT / "reports" / "html_old_gold_retest.md"
CSV_PATH = ROOT / "reports" / "html_old_gold_scores.csv"

CMS_STRIP = set(
    "class style id role tabindex target width height border cellpadding cellspacing "
    "allow allowfullscreen frameborder referrerpolicy scrolling".split()
)
CMS_PREFIX = ("aria-", "data-")
SCORE_WEIGHTS = {
    "hard": 0.45,
    "element": 0.25,
    "text": 0.30,
}


def collapse(value: str) -> str:
    """連続空白を1つにして前後空白を除去する。"""

    return re.sub(r"\s+", " ", value or "").strip()


def filtered_attrs(attrs: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """CMS由来属性を除いた比較用属性タプルを返す。"""

    result = []
    for key, value in attrs.items():
        lowered = key.lower()
        if lowered in CMS_STRIP or lowered.startswith(CMS_PREFIX):
            continue
        result.append((lowered, collapse(value or "")))
    return tuple(sorted(result))


class ParsedHtml(HTMLParser):
    """採点に必要なHTML特徴量を標準ライブラリだけで抽出する。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[tuple[str, dict[str, str]]] = []
        self.text_chunks: list[str] = []
        self.anchors: list[dict[str, Any]] = []
        self.tables: list[dict[str, Any]] = []
        self.fingerprints: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        self.in_skip = 0
        self._anchor_stack: list[dict[str, Any]] = []
        self._table_stack: list[int] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        self.tags.append(tag)
        self.attrs.append((tag, attr_map))
        self.fingerprints.append((tag, filtered_attrs(attr_map)))
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
        self.text_chunks.append(data)
        if self._anchor_stack:
            self._anchor_stack[-1]["text"].append(data)

    @property
    def visible_text(self) -> str:
        return collapse("".join(self.text_chunks))


@dataclass
class CheckResult:
    name: str
    ok: bool
    violations: int = 0
    details: list[str] = field(default_factory=list)


@dataclass
class PageScore:
    site: str
    page_id: str
    score: float
    hard_pass: int
    hard_total: int
    element_similarity: float
    text_similarity: float
    old_bytes: int
    gold_bytes: int
    old_elements: int
    gold_elements: int
    old_text_len: int
    gold_text_len: int
    checks: list[CheckResult]

    @property
    def failed_checks(self) -> list[CheckResult]:
        return [check for check in self.checks if not check.ok]

    @property
    def hard_rate(self) -> float:
        return 1.0 if self.hard_total == 0 else self.hard_pass / self.hard_total


def parse_html(path: Path) -> ParsedHtml:
    parsed = ParsedHtml()
    parsed.feed(path.read_text(encoding="utf-8", errors="replace"))
    parsed.close()
    return parsed


def load_cases() -> list[dict[str, Any]]:
    return [json.loads(line) for line in CASE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def counter_similarity(left: list[Any], right: list[Any]) -> float:
    left_counter = Counter(left)
    right_counter = Counter(right)
    intersection = sum((left_counter & right_counter).values())
    union = sum((left_counter | right_counter).values())
    return 1.0 if union == 0 else intersection / union


def check_no_tag(candidate: ParsedHtml, check: dict[str, Any]) -> CheckResult:
    values = check.get("tag", [])
    denied = set(value.lower() for value in (values if isinstance(values, list) else [values]))
    bad = [tag for tag in candidate.tags if tag in denied]
    details = [f"{tag}:{count}" for tag, count in sorted(Counter(bad).items())]
    return CheckResult("no_tag", not bad, len(bad), details)


def check_no_anchor_text(candidate: ParsedHtml, check: dict[str, Any]) -> CheckResult:
    values = check.get("value", [])
    values = values if isinstance(values, list) else [values]
    bad = [
        collapse("".join(anchor["text"]))
        for anchor in candidate.anchors
        if any(value in collapse("".join(anchor["text"])) for value in values)
    ]
    return CheckResult("no_anchor_text", not bad, len(bad), bad[:8])


def check_anchor_href_present(candidate: ParsedHtml) -> CheckResult:
    bad = [collapse("".join(anchor["text"])) for anchor in candidate.anchors if not collapse(anchor["attrs"].get("href", ""))]
    return CheckResult("anchor_href_present", not bad, len(bad), bad[:8])


def check_href_no_pattern(candidate: ParsedHtml, check: dict[str, Any]) -> CheckResult:
    pattern = re.compile(str(check.get("pattern", "")))
    bad = [attrs.get("href", "") for tag, attrs in candidate.attrs if tag == "a" and pattern.search(attrs.get("href", ""))]
    return CheckResult("href_no_pattern", not bad, len(bad), bad[:8])


def check_no_short_weekday(candidate: ParsedHtml) -> CheckResult:
    bad = re.findall(r"[（(][月火水木金土日][）)]", "".join(candidate.text_chunks))
    return CheckResult("no_short_weekday", not bad, len(bad), bad[:8])


def check_alt_present(candidate: ParsedHtml) -> CheckResult:
    bad = [attrs.get("src", "") for tag, attrs in candidate.attrs if tag == "img" and "alt" not in attrs]
    return CheckResult("alt_present", not bad, len(bad), bad[:8])


def check_no_id(candidate: ParsedHtml, check: dict[str, Any]) -> CheckResult:
    denied = set(check.get("value", []))
    bad = [attrs.get("id", "") for _, attrs in candidate.attrs if attrs.get("id") in denied]
    return CheckResult("no_id", not bad, len(bad), bad[:8])


def check_no_layout_table(candidate: ParsedHtml) -> CheckResult:
    bad = [
        table
        for table in candidate.tables
        if not table["has_th"]
        and (table["attrs"].get("border") == "0" or {"nb", "layout"} & set(table["attrs"].get("class", "").split()))
    ]
    return CheckResult("no_layout_table", not bad, len(bad), [])


def check_no_consecutive_br(raw_html: str) -> CheckResult:
    bad = re.findall(r"<br\b[^>]*>\s*(?:</br>\s*)?<br\b", raw_html, flags=re.I)
    return CheckResult("no_consecutive_br", not bad, len(bad), bad[:8])


def check_tag_count_not_decreased(candidate: ParsedHtml, baseline: ParsedHtml, check: dict[str, Any]) -> CheckResult:
    tag = str(check.get("tag", "")).lower()
    old_count = baseline.tags.count(tag)
    candidate_count = candidate.tags.count(tag)
    return CheckResult(
        "tag_count_not_decreased",
        candidate_count >= old_count,
        max(0, old_count - candidate_count),
        [f"{tag}: old={old_count}, candidate={candidate_count}"],
    )


def run_checks(candidate: ParsedHtml, baseline_old: ParsedHtml, raw_html: str, checks: list[dict[str, Any]]) -> list[CheckResult]:
    results = []
    for check in checks:
        if check.get("advisory"):
            continue
        check_type = check.get("type")
        if check_type == "no_tag":
            results.append(check_no_tag(candidate, check))
        elif check_type == "no_anchor_text":
            results.append(check_no_anchor_text(candidate, check))
        elif check_type == "anchor_href_present":
            results.append(check_anchor_href_present(candidate))
        elif check_type == "href_no_pattern":
            results.append(check_href_no_pattern(candidate, check))
        elif check_type == "no_short_weekday":
            results.append(check_no_short_weekday(candidate))
        elif check_type == "alt_present":
            results.append(check_alt_present(candidate))
        elif check_type == "no_id":
            results.append(check_no_id(candidate, check))
        elif check_type == "no_layout_table":
            results.append(check_no_layout_table(candidate))
        elif check_type == "no_consecutive_br":
            results.append(check_no_consecutive_br(raw_html))
        elif check_type == "tag_count_not_decreased":
            results.append(check_tag_count_not_decreased(candidate, baseline_old, check))
    return results


def score_page(case: dict[str, Any]) -> PageScore:
    site = str(case["site"])
    page_id = str(case["page_id"])
    old_path = FIXTURE_ROOT / site / "old" / f"{page_id}.html"
    gold_path = FIXTURE_ROOT / site / "gold" / f"{page_id}.html"
    old = parse_html(old_path)
    gold = parse_html(gold_path)
    raw = old_path.read_text(encoding="utf-8", errors="replace")
    checks = run_checks(old, old, raw, case.get("checks", []))
    hard_pass = sum(1 for check in checks if check.ok)
    hard_total = len(checks)
    hard_score = 1.0 if hard_total == 0 else hard_pass / hard_total
    element_similarity = counter_similarity(old.fingerprints, gold.fingerprints)
    text_similarity = SequenceMatcher(None, old.visible_text, gold.visible_text).ratio()
    score = 100 * (
        SCORE_WEIGHTS["hard"] * hard_score
        + SCORE_WEIGHTS["element"] * element_similarity
        + SCORE_WEIGHTS["text"] * text_similarity
    )
    return PageScore(
        site=site,
        page_id=page_id,
        score=score,
        hard_pass=hard_pass,
        hard_total=hard_total,
        element_similarity=element_similarity,
        text_similarity=text_similarity,
        old_bytes=old_path.stat().st_size,
        gold_bytes=gold_path.stat().st_size,
        old_elements=len(old.fingerprints),
        gold_elements=len(gold.fingerprints),
        old_text_len=len(old.visible_text),
        gold_text_len=len(gold.visible_text),
        checks=checks,
    )


def grade(score: float) -> str:
    if score >= 85:
        return "A"
    if score >= 75:
        return "B"
    if score >= 65:
        return "C"
    return "D"


def format_failed_checks(page: PageScore) -> str:
    if not page.failed_checks:
        return "なし"
    return ", ".join(f"`{check.name}`({check.violations})" for check in page.failed_checks)


def write_csv(scores: list[PageScore]) -> None:
    with CSV_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "page_id",
                "score",
                "grade",
                "hard",
                "element_similarity_percent",
                "text_similarity_percent",
                "old_bytes",
                "gold_bytes",
                "old_elements",
                "gold_elements",
                "old_text_len",
                "gold_text_len",
                "failed_checks",
            ]
        )
        for page in scores:
            writer.writerow(
                [
                    page.page_id,
                    f"{page.score:.1f}",
                    grade(page.score),
                    f"{page.hard_pass}/{page.hard_total}",
                    f"{page.element_similarity * 100:.1f}",
                    f"{page.text_similarity * 100:.1f}",
                    page.old_bytes,
                    page.gold_bytes,
                    page.old_elements,
                    page.gold_elements,
                    page.old_text_len,
                    page.gold_text_len,
                    ";".join(check.name for check in page.failed_checks),
                ]
            )


def aggregate_checks(scores: list[PageScore]) -> dict[str, dict[str, int]]:
    aggregate: dict[str, dict[str, int]] = defaultdict(lambda: {"pass": 0, "total": 0, "violations": 0})
    for page in scores:
        for check in page.checks:
            aggregate[check.name]["total"] += 1
            aggregate[check.name]["violations"] += check.violations
            if check.ok:
                aggregate[check.name]["pass"] += 1
    return dict(aggregate)


def write_report(scores: list[PageScore]) -> None:
    scores = sorted(scores, key=lambda page: page.page_id)
    check_summary = aggregate_checks(scores)
    average = sum(page.score for page in scores) / len(scores)
    lines = [
        "# old vs gold 全ページ再テスト結果",
        "",
        "実施日: 2026-06-09",
        "対象: `tests/fixtures/html/saga-city/old/*.html` → `tests/fixtures/html/saga-city/gold/*.html`",
        "",
        "## サマリ",
        "",
        "`old` HTML を変換前入力、`gold` HTML を人手確認済み期待出力として、全HTMLペアを同じ採点方式で再評価しました。",
        "",
        "| 指標 | 結果 |",
        "|---|---:|",
        f"| 対象ページ数 | {len(scores)} |",
        f"| 平均点 | {average:.1f} |",
        f"| 最高点 | {max(page.score for page in scores):.1f} |",
        f"| 最低点 | {min(page.score for page in scores):.1f} |",
        "",
        "## グレード分布",
        "",
        "| グレード | 点数帯 | ページ数 |",
        "|---|---:|---:|",
    ]
    grade_counts = Counter(grade(page.score) for page in scores)
    grade_ranges = {"A": "85点以上", "B": "75〜84.9点", "C": "65〜74.9点", "D": "65点未満"}
    for key in ["A", "B", "C", "D"]:
        lines.append(f"| {key} | {grade_ranges[key]} | {grade_counts.get(key, 0)} |")
    lines.extend(
        [
            "",
            "## check別集計",
            "",
            "| check | 通過ページ | 通過率 | 違反件数 |",
            "|---|---:|---:|---:|",
        ]
    )
    for name in sorted(check_summary):
        row = check_summary[name]
        pass_rate = 100 * row["pass"] / row["total"] if row["total"] else 100
        lines.append(f"| `{name}` | {row['pass']}/{row['total']} | {pass_rate:.1f}% | {row['violations']} |")
    lines.extend(
        [
            "",
            "## ページ別採点",
            "",
            "| page_id | 点数 | grade | hard | 要素類似度 | テキスト類似度 | failed checks |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for page in scores:
        lines.append(
            f"| {page.page_id} | {page.score:.1f} | {grade(page.score)} | "
            f"{page.hard_pass}/{page.hard_total} | {page.element_similarity * 100:.1f}% | "
            f"{page.text_similarity * 100:.1f}% | {format_failed_checks(page)} |"
        )
    lines.extend(
        [
            "",
            "## ページ別サイズ・特徴量",
            "",
            "| page_id | old bytes | gold bytes | old要素数 | gold要素数 | oldテキスト長 | goldテキスト長 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for page in scores:
        lines.append(
            f"| {page.page_id} | {page.old_bytes} | {page.gold_bytes} | {page.old_elements} | "
            f"{page.gold_elements} | {page.old_text_len} | {page.gold_text_len} |"
        )
    lines.extend(
        [
            "",
            "## 要対応ページ",
            "",
            "### D評価（65点未満）",
            "",
        ]
    )
    low_pages = [page for page in scores if grade(page.score) == "D"]
    if low_pages:
        for page in low_pages:
            lines.append(f"- `{page.page_id}`: {page.score:.1f}点、failed checks: {format_failed_checks(page)}")
    else:
        lines.append("- なし")
    lines.extend(["", "### failed check があるページ", ""])
    failed_pages = [page for page in scores if page.failed_checks]
    if failed_pages:
        for page in failed_pages:
            detail = ", ".join(
                f"`{check.name}`={check.violations}" for check in page.failed_checks
            )
            lines.append(f"- `{page.page_id}`: {detail}")
    else:
        lines.append("- なし")
    lines.extend(
        [
            "",
            "## 残課題と解決策",
            "",
            "### 1. 禁止タグの横断対応",
            "",
            "`no_tag` は複数ページで失敗しているため、`font`, `u`, `s`, `strike`, `i`, `center` などを意味要素またはCSS表現へ変換する共通ルールを優先して整備します。",
            "",
            "### 2. 指示語リンクの具体化",
            "",
            "`no_anchor_text` が失敗したページでは、`こちら`, `ここ`, `詳細` などのリンクテキストを、リンク先の目的が分かる具体的な文言へ置換します。",
            "",
            "### 3. 画像altと禁止hrefパターン",
            "",
            "`sg00761` は `alt_present` と `href_no_pattern` の違反件数が多いため、画像alt付与と `?smf=` / `&smf=` 付きURLの正規化を一括適用します。",
            "",
            "### 4. CMS構造差の扱い",
            "",
            "CMS由来ラッパーや見出し装飾により要素類似度が低くなるページがあります。厳密なHTML一致ではなく、本文構造・リンク・表・見出し階層・アクセシビリティ属性を主評価にするのが妥当です。",
            "",
            "## 実行コマンド",
            "",
            "```bash",
            "python reports/html_old_gold_scorer.py",
            "```",
            "",
            "同じ結果のCSVは `reports/html_old_gold_scores.csv` に保存しています。",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    scores = [score_page(case) for case in load_cases()]
    write_report(scores)
    write_csv(sorted(scores, key=lambda page: page.page_id))
    average = sum(page.score for page in scores) / len(scores)
    print(f"pages={len(scores)} average={average:.1f} report={REPORT_PATH} csv={CSV_PATH}")


if __name__ == "__main__":
    main()
