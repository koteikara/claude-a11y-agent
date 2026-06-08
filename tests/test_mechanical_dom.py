# -*- coding: utf-8 -*-
"""lxml による DOM 操作関数の回帰テスト。
シリアライズ結果の完全一致は脆いため、構造的な条件で検証する。
"""
import pytest
from lxml import html

import mechanical_rules as M


def _tree(s):
    return html.fragment_fromstring(s, create_parent="div")


def test_fix_background_color():
    t = _tree('<p style="background-color:#ff0;color:red" bgcolor="#fff">x</p>')
    M.fix_background_color(t)
    assert t.xpath("//@bgcolor") == []
    assert "background-color" not in (t.xpath("//p")[0].get("style") or "")


def test_fix_decoration_tags():
    t = _tree("<p><u>a</u><s>b</s><i>c</i>d</p>")
    M.fix_decoration_tags(t)
    assert t.xpath("//u | //s | //i") == []
    assert "".join(t.itertext()).replace(" ", "") == "abcd"


def test_fix_font_spec():
    t = _tree('<p style="font-size:14px;color:#000"><font size="3">a</font></p>')
    M.fix_font_spec(t)
    assert t.xpath("//font") == []
    assert "font-size" not in (t.xpath("//p")[0].get("style") or "")


def test_normalize_bold():
    t = _tree("<p><b>太字</b>と通常</p>")
    M.normalize_bold(t)
    assert t.xpath("//b") == []
    assert t.xpath("//strong/text()") == ["太字"]


def test_strip_table_format():
    tbl = _tree('<table style="x" class="c"><tr><td bgcolor="#fff" width="100">a</td></tr></table>').xpath("//table")[0]
    M.strip_table_format(tbl)
    assert tbl.xpath("//@style") == [] and tbl.xpath("//@class") == []
    assert tbl.xpath("//@bgcolor") == [] and tbl.xpath("//@width") == []


def test_renumber_headings():
    # h1, h4 → h2 から飛ばさず連番に
    t = _tree("<div><h1>T</h1><h4>A</h4><h4>B</h4></div>")
    M.renumber_headings(t, start_level=2)
    tags = [h.tag for h in t.xpath("//h1|//h2|//h3|//h4|//h5|//h6")]
    assert tags == ["h2", "h3", "h3"]


def test_drop_alt_equal_caption():
    t = _tree('<figure><img src="a.jpg" alt="桜の写真"><figcaption>桜の写真</figcaption></figure>')
    M.drop_alt_equal_caption(t)
    assert t.xpath("//img/@alt") == [""]


@pytest.mark.parametrize("w,expected", [(400, "sub_large"), (200, "sub_small"), (350, "sub_large")])
def test_classify_subimage(w, expected):
    assert M.classify_subimage(w) == expected


@pytest.mark.parametrize("n,rows", [(1, [1]), (3, [3]), (4, [3, 1]), (7, [3, 3, 1])])
def test_split_image_row(n, rows):
    assert M.split_image_row(n) == rows


def test_is_internal_url():
    cms = {"city.example.lg.jp"}
    umap = {"https://old.example/p1": "PAGE-1"}
    assert M.is_internal_url("https://city.example.lg.jp/x", cms, {}) is True
    assert M.is_internal_url("https://old.example/p1", set(), umap) is True
    assert M.is_internal_url("https://外部.example.com/x", cms, {}) is False


def test_normalize_bold_uppercase_style_property():
    t = _tree('<p style="FONT-WEIGHT:700;color:#000">太字</p>')
    M.normalize_bold(t)
    assert t.xpath("//strong/text()") == ["太字"]
    style = t.xpath("//p")[0].get("style") or ""
    assert "font-weight" not in style.lower()
    assert "color:#000" in style
