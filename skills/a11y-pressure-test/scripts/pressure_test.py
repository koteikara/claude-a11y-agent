#!/usr/bin/env python3
"""Run deterministic accessibility-regression pressure checks for this repo."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    command: str
    returncode: int
    duration_seconds: float
    passed: bool


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run_check(name: str, command: list[str], env: dict[str, str] | None = None) -> CheckResult:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    started = time.monotonic()
    completed = subprocess.run(command, cwd=repo_root(), env=merged_env, text=True)
    duration = time.monotonic() - started
    return CheckResult(
        name=name,
        command=" ".join(command),
        returncode=completed.returncode,
        duration_seconds=round(duration, 2),
        passed=completed.returncode == 0,
    )


def readiness(score: float) -> str:
    if score >= 95:
        return "High"
    if score >= 80:
        return "Medium"
    return "Low"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1, help="repeat each deterministic lane")
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON instead of Markdown"
    )
    args = parser.parse_args()

    if args.repeat < 1:
        parser.error("--repeat must be >= 1")

    checks: list[CheckResult] = []
    lanes = [
        ("offline-pytest", [sys.executable, "-m", "pytest", "-q"], None),
        (
            "html-pairs",
            [sys.executable, "-m", "pytest", "-q", "tests/test_html_pairs.py"],
            {"RUN_HTML_PAIRS": "1"},
        ),
    ]

    for iteration in range(1, args.repeat + 1):
        for name, command, env in lanes:
            checks.append(run_check(f"{name}#{iteration}", command, env))

    passed = sum(1 for check in checks if check.passed)
    score = round((passed / len(checks)) * 100, 1) if checks else 0.0
    payload = {
        "score": score,
        "readiness": readiness(score),
        "passed": passed,
        "total": len(checks),
        "checks": [asdict(check) for check in checks],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n## A11y Pressure-Test Summary")
        print(f"- Score: {score}% ({passed}/{len(checks)} checks passed)")
        print(f"- Readiness: {payload['readiness']}")
        print("\n| Check | Command | Result | Seconds |")
        print("|---|---|---:|---:|")
        for check in checks:
            status = "PASS" if check.passed else f"FAIL ({check.returncode})"
            print(f"| {check.name} | `{check.command}` | {status} | {check.duration_seconds} |")

    return 0 if all(check.passed for check in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
