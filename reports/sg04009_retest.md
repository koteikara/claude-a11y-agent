# sg04009 old vs gold 再テスト結果

実施日: 2026-06-09
対象: `tests/fixtures/html/saga-city/old/sg04009.html` → `tests/fixtures/html/saga-city/gold/sg04009.html`

## サマリ

`sg04009` の `old` HTML 取得後に、このページのみを再採点した結果です。
前回は `old` が空だったため総合点 45.0 点でしたが、取得後は 77.9 点まで改善しました。

| 指標 | 結果 |
|---|---:|
| 総合点 | 77.9 |
| hard check | 10/10 (100.0%) |
| 要素類似度 | 26.2% |
| テキスト類似度 | 87.9% |
| oldサイズ | 10,892 bytes |
| goldサイズ | 14,703 bytes |
| old要素数 | 137 |
| gold要素数 | 215 |
| oldテキスト長 | 2,288 |
| goldテキスト長 | 2,519 |

## hard check 結果

| check | 結果 |
|---|---|
| `no_tag` | PASS |
| `no_anchor_text` | PASS |
| `anchor_href_present` | PASS |
| `href_no_pattern` | PASS |
| `no_short_weekday` | PASS |
| `alt_present` | PASS |
| `no_id` | PASS |
| `no_layout_table` | PASS |
| `no_consecutive_br` | PASS |
| `tag_count_not_decreased` | PASS |

## 評価

- `old` の本文欠落は解消され、テキスト類似度は 87.9% まで回復しました。
- hard check は全項目 PASS です。
- 要素類似度は 26.2% に留まっています。主な理由は、`gold` 側に CMS 出力由来のラッパーや見出し装飾、テーブル表示切替用の構造が追加されているためです。
- `old` の `1.0kw` に対して `gold` は `1.0キロワット` となっており、単位表記の正規化差が残っています。
- `old` では支所ごとに `リモート窓口` リンクを持っていますが、`gold` では `各支所（リモート窓口）` とまとめられ、別途リンク項目を設けています。

## 残課題と解決策

### 1. CMS構造との差

`gold` は CMS の `free-layout-area`, `wysiwyg`, 見出し装飾用 `span`、テーブルラッパーなどを含むため、本文が近くても要素類似度は低めに出ます。

**解決策**

- 厳密な HTML 一致ではなく、本文構造・リンク・表・見出し階層・アクセシビリティ属性を主評価にする。
- E2E 比較では CMS 自動付与属性や装飾構造を正規化・除外して比較する。

### 2. 表記ゆれ

`1.0kw` と `1.0キロワット` のような単位表記差が残っています。

**解決策**

- 単位表記の正規化ルールを追加する。
  - `kw` → `キロワット`
  - 必要に応じて `cc` なども期待仕様に合わせて統一する。

### 3. 支所リンク・案内文のまとめ方

同じリンクが複数支所に繰り返される箇所で、`old` と `gold` の構造が異なっています。

**解決策**

- 同一リンクの繰り返しを `各支所（リモート窓口）` のように集約するルールを検討する。
- ただし個別支所名を残す必要があるかは、自治体側の期待仕様を確認する。

## 実行コマンド

```bash
python reports/sg04009_retest_scorer.py
```

出力:

```text
page_id=sg04009
old_bytes=10892
gold_bytes=14703
old_elements=137
gold_elements=215
old_text_len=2288
gold_text_len=2519
hard=10/10 (100.0%)
element_similarity=26.2%
text_similarity=87.9%
score=77.9
checks:
- no_tag: PASS
- no_anchor_text: PASS
- anchor_href_present: PASS
- href_no_pattern: PASS
- no_short_weekday: PASS
- alt_present: PASS
- no_id: PASS
- no_layout_table: PASS
- no_consecutive_br: PASS
- tag_count_not_decreased: PASS
```
