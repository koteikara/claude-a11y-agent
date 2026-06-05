# -*- coding: utf-8 -*-
"""LLM出力から最外部のJSONオブジェクトを取り出す堅牢パーサ。
モデルがJSON前後に説明文やコードフェンスを付けても、深さカウントで
バランスの取れた最初の {...} を抽出する（メモリの方針に準拠）。
"""
import json


def extract_json(text: str) -> dict:
    """文字列中の最外部JSONオブジェクトを dict として返す。
    見つからない/壊れている場合は ValueError。
    """
    if text is None:
        raise ValueError("empty LLM output")
    s = text.strip()
    start = s.find("{")
    if start == -1:
        raise ValueError("no '{' found in output")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        c = s[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(s[start : i + 1])
    raise ValueError("no balanced JSON object found")
