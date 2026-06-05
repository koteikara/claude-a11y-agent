# -*- coding: utf-8 -*-
"""機械+AI 16プロンプトの回帰テスト。

2モードで検証する:
  [オフライン・常時]  プロンプト雛形が全プレースホルダを埋め切り、出力契約のJSONが
                      堅牢パーサで解釈でき必須キーを持つこと。LLMは呼ばない。
  [オンライン・@llm]  実LLM（LLM_PROVIDER）を呼び、出力が契約を満たし、安定アサーション
                      （例: 2/3は日付でない）を満たすこと。RUN_LLM_TESTS=1 時のみ実行。
"""
import json
import re
from pathlib import Path

import pytest

from a11y_testkit.jsonparse import extract_json

CASES = Path(__file__).resolve().parent / "cases" / "prompt_cases.jsonl"
ALL = [json.loads(l) for l in open(CASES, encoding="utf-8") if l.strip()]

_PLACEHOLDER = re.compile(r"\{[a-zA-Z_]+\}")


def _fill(template: str, payload: dict) -> str:
    return template.format(**payload)


def _check_assertion(data, key, op, value):
    got = data.get(key)
    if op == "==":
        return got == value
    if op == "in":
        return got in value
    raise ValueError(op)


# ---------- オフライン: 雛形充填 ＋ 出力契約パース（常時実行） ----------

@pytest.mark.parametrize("c", ALL, ids=lambda c: c["id"])
def test_prompt_fills_and_contract_parses(c, prompt_templates):
    template = prompt_templates[c["rule"]]
    prompt = _fill(template, c["payload"])
    # 全プレースホルダが解決されている
    assert not _PLACEHOLDER.search(prompt), f"未解決のプレースホルダ: {prompt}"
    assert prompt.strip()
    # sample_output（前置き・コードフェンス込み）が堅牢パーサで読め、必須キーを持つ
    data = extract_json(c["sample_output"])
    for k in c["required_keys"]:
        assert k in data, f"必須キー欠落: {k}"


# ---------- オンライン: 実LLMを呼んで契約＋安定アサーション ----------

@pytest.mark.llm
@pytest.mark.parametrize("c", ALL, ids=lambda c: c["id"])
def test_prompt_live_llm(c, prompt_templates):
    from a11y_testkit.llm import llm_call

    prompt = _fill(prompt_templates[c["rule"]], c["payload"])
    raw = llm_call(prompt)
    data = extract_json(raw)  # 契約JSONが取り出せること
    for k in c["required_keys"]:
        assert k in data, f"必須キー欠落: {k} / 生出力: {raw[:200]}"
    for key, op, value in c.get("assertions", []):
        assert _check_assertion(data, key, op, value), \
            f"{c['id']} 失敗: {key} {op} {value} / got={data.get(key)}"
