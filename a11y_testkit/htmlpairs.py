# -*- coding: utf-8 -*-
"""HTMLペア回帰テスト用の共有ヘルパ。"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable

from lxml import etree, html

CMS_ATTRS_TO_STRIP = {
    "class",
    "style",
    "id",
    "role",
    "tabindex",
    "target",
    "width",
    "height",
    "border",
    "cellpadding",
    "cellspacing",
    "allow",
    "allowfullscreen",
    "frameborder",
    "referrerpolicy",
    "scrolling",
}
CMS_ATTR_PREFIXES_TO_STRIP = ("aria-", "data-")


def strip_cms_attrs(tree):
    """CMS自動付与属性をツリーから破壊的に除去して返す。

    ドリフト/E2E比較時に ``copy.deepcopy`` したツリーへ適用する想定。
    ``href`` / ``src`` / ``alt`` / ``title`` / ``lang`` など意味属性は残す。
    """

    for el in _iter_elements(tree):
        for name in list(el.attrib):
            lowered = _local_attr_name(name).lower()
            if lowered in CMS_ATTRS_TO_STRIP or lowered.startswith(CMS_ATTR_PREFIXES_TO_STRIP):
                del el.attrib[name]
    return tree


def normalized_html(tree, *, strip_cms: bool = True) -> str:
    """比較用に属性順と空白を正規化したHTML文字列を返す。"""

    work = copy.deepcopy(tree)
    if strip_cms:
        strip_cms_attrs(work)
    _normalize_node(work)
    return etree.tostring(work, encoding="unicode", method="html", with_tail=False)


def element_fingerprints(tree, *, strip_cms: bool = True) -> list[str]:
    """差分件数化用に、要素単位の正規化フィンガープリントを返す。"""

    work = copy.deepcopy(tree)
    if strip_cms:
        strip_cms_attrs(work)
    _normalize_node(work)
    return [_fingerprint(el) for el in _iter_elements(work)]


def drift_element_diff_count(left, right) -> int:
    """正規化後の要素フィンガープリント差分数を返す。"""

    left_items = element_fingerprints(left)
    right_items = element_fingerprints(right)
    common = 0
    used = [False] * len(right_items)
    for item in left_items:
        for idx, other in enumerate(right_items):
            if not used[idx] and item == other:
                used[idx] = True
                common += 1
                break
    return (len(left_items) - common) + (len(right_items) - common)


def visible_text_len(tree) -> int:
    """script/style配下を除いた可視テキスト相当の長さを返す。"""

    chunks = []
    for text in tree.xpath(".//text()[not(ancestor::script) and not(ancestor::style)]"):
        chunks.append(str(text))
    return len(_collapse_ws("".join(chunks)))


def _iter_elements(tree) -> Iterable[etree._Element]:
    if isinstance(tree, etree._ElementTree):
        root = tree.getroot()
    else:
        root = tree
    if root is None:
        return []
    return root.iter()


def _local_attr_name(name: str) -> str:
    if name.startswith("{"):
        return name.rsplit("}", 1)[-1]
    return name


def _normalize_node(node) -> None:
    for el in _iter_elements(node):
        if el.text is not None:
            el.text = _collapse_ws(el.text)
        if el.tail is not None:
            el.tail = _collapse_ws(el.tail)
        if el.attrib:
            items = sorted(el.attrib.items(), key=lambda item: item[0])
            el.attrib.clear()
            for key, value in items:
                el.set(key, _collapse_ws(value))


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _fingerprint(el) -> str:
    attrs = tuple(sorted((k, _collapse_ws(v)) for k, v in el.attrib.items()))
    text = _collapse_ws("".join(el.itertext()))
    return repr((el.tag, attrs, text))


def parse_html_document(source: str | bytes):
    """HTML全文または断片をlxml要素として堅牢にパースする。"""

    data = source.encode("utf-8", errors="replace") if isinstance(source, str) else source
    parser = html.HTMLParser(encoding="utf-8", recover=True)
    try:
        return html.fromstring(data, parser=parser)
    except (etree.ParserError, ValueError):
        return html.fragment_fromstring(data, create_parent="div", parser=parser)
