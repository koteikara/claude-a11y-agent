---
name: a11y-pressure-test
description: Stress-test accessibility regression fixes in this repository and estimate issue-resolution readiness. Use when Codex is asked to validate an a11y migration fix, pressure test changes, measure implementation feasibility/completeness, or summarize residual risk before merging changes to mechanical rules, prompt contracts, HTML fixtures, or regression cases.
---

# A11y Pressure Test

## Goal

Validate an accessibility-regression issue fix under repeatable offline checks, then report how ready the fix is to merge and what evidence supports that judgement.

## Workflow

1. Identify the issue scope:
   - mechanical text or DOM rule changes: inspect `mechanical_rules.py` and `tests/cases/mechanical_cases.jsonl`.
   - prompt contract changes: inspect `specs/a11y_hybrid_detect_fix.jsonl` and `tests/cases/prompt_cases.jsonl`.
   - HTML migration fixtures: inspect `tests/cases/html_pairs.jsonl` and matching `tests/fixtures/html/{site}/{old,ai,gold}/` files.
2. Add or update the smallest regression case that proves the issue is fixed.
3. Run the pressure harness:
   ```bash
   python skills/a11y-pressure-test/scripts/pressure_test.py --repeat 2
   ```
4. If the issue touches HTML fixtures, include the HTML-pair pass in the readiness judgement. The harness runs it with `RUN_HTML_PAIRS=1`.
5. If live LLM behavior is explicitly in scope and credentials are available, run the relevant `pytest -m llm` command separately; otherwise treat live LLM confidence as unmeasured, not failed.
6. Report:
   - score and readiness band from the harness,
   - checks executed and their pass/fail status,
   - issue-specific regression cases added or exercised,
   - remaining risks and next actions.

## Readiness Bands

Use `references/readiness-rubric.md` when translating pressure-test results into a merge recommendation.

## Notes

- Prefer deterministic offline evidence over anecdotal manual review.
- Do not hide skipped live-LLM checks; list them as out of scope or environment-limited.
- Keep generated reports outside the repository unless the user asks to commit them.
