# A11y Pressure-Test Readiness Rubric

Use this rubric after running `scripts/pressure_test.py`.

| Band | Score | Meaning | Recommendation |
|---|---:|---|---|
| High | 95-100 | Offline regression checks repeatedly pass; remaining risk is narrow or explicitly out of scope. | Ready to merge after normal review. |
| Medium | 80-94 | Most checks pass, but a non-critical lane is flaky, skipped, or not applicable. | Merge only if residual risk is accepted and follow-up is tracked. |
| Low | 0-79 | One or more critical deterministic checks fail. | Do not merge; fix failures and rerun pressure test. |

Critical lanes for this repository:

1. `pytest -q` for mechanical rules, prompt-template contracts, and always-on regression tests.
2. `RUN_HTML_PAIRS=1 pytest -q tests/test_html_pairs.py` when HTML fixture behavior or migration quality is part of the issue.
3. Issue-specific regression cases that exercise the reported failure mode.

When live LLM tests are unavailable, score only deterministic lanes and explicitly state that live model behavior was not measured.
