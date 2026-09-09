"""Run structural evaluations against the Clone & Scan HTTP API.

Usage:
    python -m eval.evaluate --base-url http://localhost:8000

The runner deliberately uses structural checks instead of an LLM judge by
 default. This keeps golden evaluations reproducible and makes failures
 actionable: each criterion is printed with its observed result.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_DATASET = Path(__file__).with_name("golden_dataset.json")


@dataclass
class TaskResult:
    task_id: str
    passed: bool
    checks: list[str]
    report: str = ""


def _request_json(url: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach {url}: {exc.reason}") from exc


def submit_and_poll(base_url: str, task: dict[str, Any], timeout_seconds: int) -> str:
    """Submit one job and return its completed report."""
    response = _request_json(
        f"{base_url.rstrip('/')}/research",
        method="POST",
        payload={"repo_path": task["repo_path"], "query": task["query"]},
    )
    job_id = response.get("job_id")
    if not job_id:
        raise RuntimeError(f"API response did not include job_id: {response}")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = _request_json(f"{base_url.rstrip('/')}/jobs/{job_id}")
        if job.get("status") == "done":
            return job.get("report", "")
        if job.get("status") == "failed":
            raise RuntimeError(f"Job {job_id} failed: {job.get('error', 'unknown error')}")
        time.sleep(2)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout_seconds}s")


def _contains_any(report: str, terms: list[str]) -> bool:
    lowered = report.casefold()
    return any(term.casefold() in lowered for term in terms)


def evaluate_report(task: dict[str, Any], report: str) -> TaskResult:
    """Apply deterministic quality and grounding checks to one report."""
    criteria = task["expected_criteria"]
    lowered = report.casefold()
    checks: list[str] = []
    passed = True

    for section in criteria.get("required_sections", []):
        ok = section.casefold() in lowered
        checks.append(f"required section '{section}': {'PASS' if ok else 'FAIL'}")
        passed &= ok

    for field, label in (
        ("required_any_terms", "content"),
        ("required_any_architecture_terms", "architecture"),
        ("required_any_remediation_terms", "remediation"),
        ("required_any_scope_terms", "scope"),
    ):
        terms = criteria.get(field, [])
        if terms:
            ok = _contains_any(report, terms)
            checks.append(f"required {label} evidence: {'PASS' if ok else 'FAIL'}")
            passed &= ok

    for term in criteria.get("forbidden_terms", []):
        ok = term.casefold() not in lowered
        checks.append(f"forbidden term '{term}': {'PASS' if ok else 'FAIL'}")
        passed &= ok

    citation_count = len(re.findall(r"\bLines?\s+\d+(?:\s*[-–]\s*\d+)?\b", report, re.IGNORECASE))
    minimum = int(criteria.get("min_citations", 0))
    citation_ok = citation_count >= minimum
    checks.append(f"citations {citation_count}/{minimum}: {'PASS' if citation_ok else 'FAIL'}")
    passed &= citation_ok

    return TaskResult(task_id=task["id"], passed=passed, checks=checks, report=report)


def load_dataset(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        dataset = json.load(handle)
    if not isinstance(dataset, list) or len(dataset) < 5:
        raise ValueError("Golden dataset must contain at least five task objects")
    ids = [task.get("id") for task in dataset]
    if any(not task_id for task_id in ids) or len(set(ids)) != len(ids):
        raise ValueError("Golden task IDs must be present and unique")
    return dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--timeout", type=int, default=600, help="Per-task timeout in seconds")
    args = parser.parse_args()

    try:
        tasks = load_dataset(args.dataset)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Dataset error: {exc}", file=sys.stderr)
        return 2

    results: list[TaskResult] = []
    for task in tasks:
        print(f"\n[{task['id']}] submitting {task['repo_path']}")
        try:
            report = submit_and_poll(args.base_url, task, args.timeout)
            result = evaluate_report(task, report)
        except (TimeoutError, RuntimeError) as exc:
            result = TaskResult(task_id=task["id"], passed=False, checks=[f"execution: FAIL ({exc})"])
        results.append(result)
        print(f"{'PASS' if result.passed else 'FAIL'}: {task['id']}")
        for check in result.checks:
            print(f"  - {check}")

    passed = sum(result.passed for result in results)
    total = len(results)
    print("\n=== Evaluation Summary ===")
    print(f"Passed: {passed}/{total}")
    print(f"Pass rate: {passed / total:.1%}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
