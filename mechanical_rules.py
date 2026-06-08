# -*- coding: utf-8 -*-
"""
mechanical_rules.py — 「機械」処理32ルールの実装メモ
=====================================================
Claude-A11y Agent v2.0 の Rule ステージ向け。検出も修正も決定的に行える32ルールを、
正規表現・置換テーブル・lxml操作の3系統に整理したリファレンス実装です。
- テーブル類は代表値のみ収録（… で示す箇所は本番で拡張）。
- lxml 関数は受け取った要素ツリーを破壊的に編集する想定。
- 出典ページは各ルールIDの docstring 参照（a11y_migration_rules_classified.jsonl と対応）。

★実装上の最重要注意（COMMON-M-01）★
  単位・記号・語句の置換は必ず「語境界」を確認してから行う。誤爆例:
    "CM"→"センチメートル" で "CMYK"→"センチメートルYK"
    "g"→"グラム"        で "grade"→"グラムrade"
    "TEL"→"電話"        で "HOTEL"→"HO電話"  ← R-18は語境界NG時は質問へ回す
  数値・小数・桁区切りはこのモジュールでは一切いじらない（LLMにも渡さない）。
"""

import re
from urllib.parse import urlparse

from lxml import etree, html

# ============================================================================
# 系統A: 文字列置換テーブル
# ============================================================================

# --- HTML-R-07 機種依存文字 → 代替文字（p35） ---------------------------------
# 丸数字・ローマ数字・単位記号・略字・囲み文字など。※代表値、本番は要拡張。
KISYU_IZON = {
    "①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5",
    "⑥": "6", "⑦": "7", "⑧": "8", "⑨": "9", "⑩": "10",
    "Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅳ": "4", "Ⅴ": "5",
    "㈱": "（株）", "㈲": "（有）", "㈹": "（代）",
    "℡": "電話", "№": "No.", "㎡": "平方メートル", "㎏": "キログラム",
    "㎝": "センチメートル", "㎜": "ミリメートル", "㎞": "キロメートル",
    "㊤": "（上）", "㊦": "（下）", "㍻": "平成", "㍼": "昭和",
    # … 半角カナ・特殊罫線・その他環境依存文字を追加
}
_KISYU_RE = re.compile("|".join(map(re.escape, sorted(KISYU_IZON, key=len, reverse=True))))

def fix_kisyu_izon(text: str) -> str:
    """HTML-R-07: 機種依存文字をテーブルで置換。"""
    return _KISYU_RE.sub(lambda m: KISYU_IZON[m.group()], text)


# --- HTML-R-10 全角英数字 → 半角（p28） --------------------------------------
# 全角英大小文字・数字・一部記号のみ半角化。和文記号（、。「」）は対象外。
_ZEN2HAN = str.maketrans(
    {chr(c): chr(c - 0xFEE0) for c in range(0xFF01, 0xFF5F)}  # ！-｝ → !-}
)
def fix_fullwidth_alnum(text: str) -> str:
    """HTML-R-10: 全角英数字・記号を半角へ。全角スペースは別途R-17で扱う。"""
    return text.translate(_ZEN2HAN)


# --- HTML-R-09 通貨・単位 → カタカナ表記（p27） -------------------------------
# 数値の直後に来る単位のみ置換。語境界（直後が英字でない）を必須にして誤爆回避。
UNIT_KANA = {
    "¥": "円", "￥": "円",
    "cm": "センチメートル", "mm": "ミリメートル", "km": "キロメートル", "m": "メートル",
    "kg": "キログラム", "mg": "ミリグラム", "g": "グラム", "t": "トン",
    "ml": "ミリリットル", "l": "リットル", "L": "リットル",
    "m2": "平方メートル", "km2": "平方キロメートル", "ha": "ヘクタール",
    "%": "パーセント",
    # … ℃, dB, kWh など必要に応じ追加
}
# 数値（小数・桁区切り可）＋単位、ただし単位の直後が英字なら除外（CMYK等）
_UNIT_RE = re.compile(
    r"(?P<num>\d[\d,\.]*)\s*(?P<unit>m2|km2|cm|mm|km|kg|mg|ml|ha|[mgltL%¥￥])(?![A-Za-z])"
)
def fix_units(text: str) -> str:
    """HTML-R-09: 「数値＋単位」をカタカナ単位に。数値そのものは保持。"""
    def _rep(mch):
        unit = mch.group("unit")
        return f'{mch.group("num")}{UNIT_KANA.get(unit, unit)}'
    # ¥は数値の前に来る場合があるので別処理
    text = re.sub(r"[¥￥]\s*(\d[\d,\.]*)", r"\1円", text)
    return _UNIT_RE.sub(_rep, text)


# --- HTML-R-18 TEL/FAX 表記の修正（p28） -------------------------------------
# 変換先は自治体別。語境界必須。語の一部（HOTEL, FAXED等）は変換せず質問キューへ。
TELFAX_MAP = {           # ← 自治体設定で差し替え
    "TEL": "電話番号", "Tel": "電話番号", "tel": "電話番号",
    "FAX": "ファックス", "Fax": "ファックス", "fax": "ファックス",
}
# 前後が英字でない＝独立トークンのときだけ置換
_TELFAX_RE = re.compile(r"(?<![A-Za-z])(TEL|Tel|tel|FAX|Fax|fax)(?![A-Za-z])")
_TELFAX_INWORD_RE = re.compile(r"[A-Za-z]*(TEL|FAX)[A-Za-z]+|[A-Za-z]+(TEL|FAX)[A-Za-z]*", re.I)

def fix_telfax(text: str):
    """HTML-R-18: 独立した TEL/FAX のみ置換。語中に含まれる場合は質問フラグを返す。"""
    needs_review = bool(_TELFAX_INWORD_RE.search(text))   # HOTEL 等
    fixed = _TELFAX_RE.sub(lambda m: TELFAX_MAP[m.group(1)], text)
    return fixed, needs_review


# ============================================================================
# 系統B: 正規表現による除去・抽出・整形
# ============================================================================

# --- HTML-R-17 段落冒頭スペースは保持＋全角→半角（p21） ----------------------
_LEADING_WS_RE = re.compile(r"^([\s\u3000]+)")
def fix_leading_space(text: str) -> str:
    """HTML-R-17: 段落冒頭の連続スペースは削除せず、全角(\u3000)を半角に統一。"""
    m = _LEADING_WS_RE.match(text)
    if not m:
        return text
    lead = m.group(1).replace("\u3000", " ")
    return lead + text[m.end():]


# --- HTML-R-04 単語内の不要なスペース・改行削除（p21） ------------------------
# 日本語文字（CJK/かな）どうしの間のスペース・改行のみ削除。英数字間は保持。
# ※R-17で保護した冒頭スペースには適用しない（行頭以外に限定）。
_CJK = r"\u3040-\u30FF\u3400-\u9FFF\uF900-\uFAFF\uFF66-\uFF9F"
_INWORD_WS_RE = re.compile(rf"(?<=[{_CJK}])[ \t\u3000\r\n]+(?=[{_CJK}])")
def fix_inword_space(text: str) -> str:
    """HTML-R-04: 日本語文字間のスペース/改行を除去。"""
    return _INWORD_WS_RE.sub("", text)


# --- FILE-R-02 リンク文言内の形式・容量表記削除（p53） -----------------------
# 例: 「申請書(PDF: 2MB)」「○○ [Word 1.2 MB]」「（ＰＤＦ：３００ＫＢ）」
_FILE_TYPE_PAT = (
    r"PDF|ＰＤＦ|Word|Ｗｏｒｄ|Excel|Ｅｘｃｅｌ|PowerPoint|ＰｏｗｅｒＰｏｉｎｔ|"
    r"DOCX?|ＤＯＣＸ?|XLSX?|ＸＬＳＸ?|PPTX?|ＰＰＴＸ?|ZIP|ＺＩＰ|テキスト"
)
_FILEMETA_RE = re.compile(
    rf"\s*[（(\[【]\s*(?:{_FILE_TYPE_PAT})?"
    r"[\s:：]*[\d０-９]+(?:[.．][\d０-９]+)?\s*(?:[KMGＫＭＧ]?[BＢ]|バイト)\s*[)）\]】]",
    re.IGNORECASE,
)
def strip_file_meta(text: str) -> str:
    """FILE-R-02: 自動表示されるファイル形式・容量の括弧表記を削除。"""
    return _FILEMETA_RE.sub("", text)


# --- SKIP-02 PDF閲覧ソフトDLリンク / SKIP-03 Weblio用語解説（p17） ------------
_ADOBE_TXT_RE = re.compile(r"(Adobe\s*(Acrobat\s*)?Reader|アクロバット\s*リーダー)", re.I)
_VIEWER_HOST_RE = re.compile(r"get\.adobe\.com|adobe\.com/.*reader", re.I)
_WEBLIO_HOST_RE = re.compile(r"(?:^|//|\.)weblio\.jp", re.I)

def is_skip_link(href: str, anchor_text: str) -> bool:
    """SKIP-02/03: 移行不要リンク（Reader DL / Weblio用語解説）を判定。"""
    blob = f"{href} {anchor_text}"
    return bool(_VIEWER_HOST_RE.search(blob) or _ADOBE_TXT_RE.search(anchor_text)
                or _WEBLIO_HOST_RE.search(href))


# --- MAP-R-02 「大きな地図を見る」リンク削除（p88） --------------------------
_BIGMAP_RE = re.compile(r"大きな地図(を見る|で見る)?")
def is_bigmap_link(href: str, anchor_text: str) -> bool:
    """MAP-R-02: GoogleMapが自動表示する誘導リンクを判定（href側はmaps系で補強）。"""
    return bool(_BIGMAP_RE.search(anchor_text)) or "maps.google" in href or "google.com/maps" in href


# --- MOBILE-R-02 携帯: 見出し3/4相当に「■」付与（p91） / R-04 戻るリンク削除 ----
_BACKTOP_RE = re.compile(r"(トップ(ページ)?へ(戻る|もどる)|ページの先頭へ)")
def is_backtop_link(anchor_text: str) -> bool:
    """MOBILE-R-04: 自動表示される「トップへ戻る」系リンクを判定し削除対象に。"""
    return bool(_BACKTOP_RE.search(anchor_text))

def mobile_subheading(text: str) -> str:
    """MOBILE-R-02: 携帯ページの見出し3/4相当テキストの先頭に ■ を付与。"""
    return text if text.startswith("■") else "■" + text


# ============================================================================
# 系統C: lxml による DOM 操作
# ============================================================================

def strip_inline_style(el, props):
    """指定CSSプロパティを style 属性から除去するヘルパ。"""
    style = el.get("style")
    if not style:
        return
    kept = [d for d in style.split(";")
            if d.strip() and d.split(":", 1)[0].strip().lower() not in props]
    if kept:
        el.set("style", ";".join(kept).strip())
    else:
        el.attrib.pop("style", None)

def unwrap(el):
    """タグを外して中身（テキスト・子要素）を親に残す。el.text と el.tail を保全。"""
    parent = el.getparent()
    if parent is None:
        return
    idx = parent.index(el)
    text = el.text or ""
    children = list(el)
    tail = el.tail or ""

    def _sink(s):
        # idx位置の直前のテキスト格納先（親text or 直前要素のtail）へ文字列を足す
        if idx == 0:
            parent.text = (parent.text or "") + s
        else:
            prev = parent[idx - 1]
            prev.tail = (prev.tail or "") + s

    _sink(text)
    for j, child in enumerate(children):
        parent.insert(idx + j, child)
    if children:                       # tail は末尾子要素のtailへ
        children[-1].tail = (children[-1].tail or "") + tail
    else:                              # 子が無ければテキスト格納先へ
        _sink(tail)
    parent.remove(el)


def fix_background_color(tree):
    """HTML-R-03: 背景色指定（style:background-color / bgcolor）を全除去。"""
    for el in tree.xpath("//*[@style or @bgcolor]"):
        el.attrib.pop("bgcolor", None)
        strip_inline_style(el, {"background-color", "background"})


def fix_decoration_tags(tree):
    """HTML-R-11: 下線/打消し/斜体を解除（タグはunwrap、styleは除去）。"""
    for el in tree.xpath("//u | //s | //strike | //i | //em[not(@*)]"):
        unwrap(el)
    for el in tree.xpath("//*[@style]"):
        strip_inline_style(el, {"text-decoration", "font-style"})


def fix_font_spec(tree):
    """HTML-R-20: 文字サイズ・フォント指定を除去（<font>解除＋style除去）。"""
    for el in tree.xpath("//font"):
        unwrap(el)
    for el in tree.xpath("//*[@style]"):
        strip_inline_style(el, {"font-size", "font-family", "font"})


def normalize_bold(tree):
    """HTML-R-02: 太字を保持しつつ <b>→<strong>、font-weight:bold→<strong>へ正規化。"""
    for el in tree.xpath("//b"):
        el.tag = "strong"
    for el in tree.xpath("//*[@style]"):
        style = el.get("style", "")
        if re.search(r"font-weight\s*:\s*(bold|[6-9]00)", style, re.I):
            strong = etree.SubElement(el, "strong")
            strong.text = el.text or ""
            el.text = None
            for c in list(el)[:-1]:
                strong.append(c)
        strip_inline_style(el, {"font-weight"})


def strip_table_format(table):
    """HTML-R-14: 表の書式解除（style/クラス/インライン装飾を除去、構造は保持）。"""
    for el in table.iter():
        el.attrib.pop("style", None)
        el.attrib.pop("class", None)
        el.attrib.pop("bgcolor", None)
        el.attrib.pop("width", None)
        el.attrib.pop("height", None)


def renumber_headings(tree, start_level=2):
    """HTML-R-12: 本文の見出しを h2 から開始し、階層を飛ばさず連続化。
    既存hタグの相対的な深さ順序は維持したまま、絶対レベルを詰める。"""
    headings = tree.xpath("//h1|//h2|//h3|//h4|//h5|//h6")
    prev_src, cur = 0, start_level - 1
    level_map = {}
    for h in headings:
        src = int(h.tag[1])
        if src > prev_src:
            cur += 1                     # 一段深く（ただし飛ばさない）
        elif src < prev_src:
            cur = max(start_level, cur - (prev_src - src))
        cur = max(cur, start_level)
        level_map[h] = cur
        prev_src = src
    for h, lv in level_map.items():
        h.tag = f"h{min(lv, 6)}"


def drop_alt_equal_caption(tree):
    """IMG-R-04: 直近のキャプションと画像名(alt)が同一なら alt を空に（省略）。"""
    for img in tree.xpath("//img[@alt]"):
        alt = (img.get("alt") or "").strip()
        # figure>figcaption もしくは直後/直前のキャプション要素を想定
        caps = img.xpath("ancestor::figure[1]/figcaption/text()")
        caps += img.xpath("following-sibling::*[contains(@class,'caption')][1]//text()")
        if any(alt and alt == c.strip() for c in caps):
            img.set("alt", "")


# --- IMG-R-07 表示幅でサブ画像大/小（p55-56）/ IMG-R-08 横並び枚数（p57） -----
SUBIMG_THRESHOLD_PX = 350          # 目安。コンテンツ幅の約50%
def classify_subimage(width_px: int) -> str:
    """IMG-R-07: 画像の表示幅から large/small パーツを選択。"""
    return "sub_large" if width_px and width_px >= SUBIMG_THRESHOLD_PX else "sub_small"

ROW_IMAGE_MAX = 3                  # 横並びは3枚まで（template 0005）
def split_image_row(image_count: int):
    """IMG-R-08: 横並び枚数から、行数と各行枚数（最大3）を返す。"""
    rows = [min(ROW_IMAGE_MAX, image_count - i) for i in range(0, image_count, ROW_IMAGE_MAX)]
    return rows


# ============================================================================
# 系統D: URL / ドメイン判定 ＋ 移行管理シート照合
# ============================================================================

def is_internal_url(href: str, cms_domains: set, url_map: dict) -> bool:
    """LINK-R-01: CMS管理ドメイン または 移行管理シートに新URLがあるものを内部とみなす。"""
    if href.startswith(("#", "mailto:", "tel:")):
        return False
    if href in url_map:                       # 旧URL→新ページIDが存在
        return True
    parsed = urlparse(href)
    if not parsed.scheme and not parsed.netloc:
        return True
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return False
    host = parsed.netloc.lower()
    return any(host == d or host.endswith("." + d) for d in cms_domains)

_FILE_EXT_RE = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|csv)(\?|$)", re.I)
def is_external_file_link(href: str, cms_domains: set) -> bool:
    """LINK-R-05: 外部ドメイン上のファイルは（転載せず）外部リンク扱い。"""
    return bool(_FILE_EXT_RE.search(href)) and not is_internal_url(href, cms_domains, {})

def resolve_internal_link(href: str, url_map: dict):
    """LINK-W-01: 取込時に外部化された内部リンクを、URL照合で新ページIDに再設定。"""
    return url_map.get(href)                  # None なら手動確認へ

def external_link_name(target_title: str, site_name: str, is_top: bool) -> str:
    """LINK-R-07: 外部リンク名を「ページタイトル（サイト名）」/「サイト名 トップページ」に整形。"""
    return f"{site_name} トップページ" if is_top else f"{target_title}（{site_name}）"


# ============================================================================
# 系統E: 位置・マーカー検出（除外/スコープ系）
# ============================================================================

_UPDATED_RE = re.compile(r"(更新日|最終更新|掲載日)[\s:：]*\d")
def is_updated_date_line(text: str) -> bool:
    """SKIP-01: 更新日表示（原則移行不要、自治体別ルール有）を判定。"""
    return bool(_UPDATED_RE.search(text))

MIGRATION_SOURCE_MARKER = "移行元データ"
def drop_migration_source_block(tree):
    """SKIP-05: ページ末尾の「移行元データ」ブロックを削除（公開前必須）。"""
    for el in tree.xpath(f"//*[contains(text(),'{MIGRATION_SOURCE_MARKER}')]"):
        # マーカー見出し以降を末尾まで除去する想定（実装はサイト構造に合わせ調整）
        p = el.getparent()
        if p is not None:
            p.remove(el)

def is_mobile_page(page_meta: dict) -> bool:
    """MOBILE-R-01: 携帯カテゴリ配下ならA11y修正系ルールを丸ごとスキップ。
    MOBILE-R-03（tel自動リンク）も携帯では無処理＝このフラグで分岐。"""
    return page_meta.get("category") == "mobile"


# ============================================================================
# 適用順の指針（パイプライン）
# ============================================================================
# 1) is_mobile_page で携帯を分離（MOBILE-R-01）
# 2) テキスト系: R-17(冒頭保護) → R-04(語内除去) → R-07 → R-10 → R-09 → R-18
#    ※R-17を先に通し、保護した冒頭スペースをR-04が触らないこと
# 3) DOM系: normalize_bold → fix_background_color → fix_decoration_tags
#           → fix_font_spec → strip_table_format → renumber_headings
# 4) リンク/画像/除外系: 各 is_* 判定でフラグ付け → 除去・再設定
# 5) R-09/R-18 は needs_review/誤爆チェックの戻り値を必ず質問キューに集約
