# -*- coding: utf-8 -*-
"""Dataclasses shared by the runner and engine adapter."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReviewItem:
    kind: str
    rule_id: str
    message: str
    location: str
    suggestion: str | None = None


@dataclass
class PageResult:
    ai_html: str
    mechanical_fixes: list[dict] = field(default_factory=list)
    llm_fixes: list[dict] = field(default_factory=list)
    needs_review: list[ReviewItem] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
