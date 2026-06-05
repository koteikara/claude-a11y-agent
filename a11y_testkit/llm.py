# -*- coding: utf-8 -*-
"""LLM抽象化レイヤ（Claude-A11y Agent v2.0 の LLM 層に合わせた薄いラッパ）。

- LLM_PROVIDER 環境変数で "gemini" / "claude" を切替（既定: gemini）。
- 本番では agent 側の実装に差し替える。ここはテスト雛形用の最小参照実装。
- import は遅延させ、オフラインテスト（Mock使用）ではSDK不要にする。
"""
import os

PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")


def llm_call(prompt: str, image_b64: str | None = None, image_mime: str = "image/jpeg") -> str:
    """プロンプト（必要なら画像）を渡し、生のテキスト応答を返す。"""
    if PROVIDER == "gemini":
        return _gemini(prompt, image_b64, image_mime)
    if PROVIDER == "claude":
        return _claude(prompt, image_b64, image_mime)
    raise RuntimeError(f"unknown LLM_PROVIDER: {PROVIDER}")


def _gemini(prompt, image_b64, image_mime):
    import base64
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(GEMINI_MODEL)
    parts = [prompt]
    if image_b64:
        parts.append({"mime_type": image_mime, "data": base64.b64decode(image_b64)})
    return model.generate_content(parts).text


def _claude(prompt, image_b64, image_mime):
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    content = [{"type": "text", "text": prompt}]
    if image_b64:
        content.insert(0, {
            "type": "image",
            "source": {"type": "base64", "media_type": image_mime, "data": image_b64},
        })
    msg = client.messages.create(
        model=CLAUDE_MODEL, max_tokens=1024,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class MockLLM:
    """オフラインテスト用。事例の sample_output をそのまま返す。"""

    def __init__(self, scripted: dict):
        self._scripted = scripted  # {case_id: output_text}

    def for_case(self, case_id: str):
        out = self._scripted[case_id]
        return lambda prompt, image_b64=None, image_mime="image/jpeg": out
