#!/usr/bin/env python3
"""Execute the example, collect evidence, and check four decisions."""
import argparse
import ast
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.util
import inspect
import io
import json
from pathlib import Path
import platform

from evaluate import digest, evaluate, read_json

ROOT = Path(__file__).resolve().parents[1]


def collect(path, policy):
    source = path.read_text(encoding="utf-8")
    spec = importlib.util.spec_from_file_location("demo_variant", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    export = module.export_rows

    def run(rows, formatter=str):
        sink, stdout = [], io.StringIO()
        with contextlib.redirect_stdout(stdout):
            result = export(rows, sink.append, formatter)
        return result, sink, stdout.getvalue()

    values = {}
    cases = [[], ["a", "b"], ["привет", "🛠", ""]]
    values["correctness"] = all(run(rows)[:2] == (tuple(rows), rows) for rows in cases)
    signature = inspect.signature(export)
    values["api_contract"] = (
        list(signature.parameters) == ["rows", "emit", "formatter"]
        and signature.parameters["formatter"].default is str
        and signature.parameters["rows"].default is inspect.Parameter.empty
        and signature.parameters["emit"].default is inspect.Parameter.empty
    )
    invalid_sink = []
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            export(["a", 5], invalid_sink.append)
    except ValueError:
        values["input_validation"] = not invalid_sink
    else:
        values["input_validation"] = False
    values["testability"] = all(run(rows)[2] == "" for rows in cases)
    values["extensibility"] = run(["alpha", "beta"], str.upper)[:2] == (
        ("ALPHA", "BETA"), ["ALPHA", "BETA"])
    first = run(["client-a"])
    second = run(["client-b", "other"])
    values["reusability"] = first[:2] == (("client-a",), ["client-a"]) and second[:2] == (
        ("client-b", "other"), ["client-b", "other"])
    branch_types = (ast.If, ast.IfExp, ast.For, ast.While, ast.Try, ast.BoolOp, ast.comprehension)
    values["branch_nodes"] = sum(isinstance(node, branch_types) for node in ast.walk(ast.parse(source)))
    values["source_lines"] = sum(bool(line.strip()) and not line.lstrip().startswith("#") for line in source.splitlines())
    calls = []

    def formatter(value):
        calls.append(value)
        return value

    run(["a", "b", "c"], formatter)
    values["formatter_calls"] = values["work_budget"] = len(calls)
    collector_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
    return {
        "schema_version": 2, "policy_sha256": digest(policy), "scope": policy["scope"],
        "suite_id": policy["suite_id"], "source_revision": hashlib.sha256(source.encode()).hexdigest(),
        "environment": f"{platform.python_implementation()}-{platform.python_version()}/{platform.system()}-{platform.machine()}/collector-{collector_hash}",
        "experiment_id": "export-rows-demo-v2", "collected_at": datetime.now(timezone.utc).isoformat(),
        "measurements": {metric["id"]: {"status": "measured", "value": values[metric["id"]],
            "evidence": f"{path.name}: {metric['method']}"}
            for metric in policy["hard_constraints"] + policy["levels"]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("production", "mvp", "realtime"), default="production")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "demo/reports")
    args = parser.parse_args()
    policy = read_json(ROOT / f"configs/{args.profile}.json")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports = {}
    for variant in ("baseline", "testable", "compact-regression", "efficient"):
        reports[variant] = collect(ROOT / f"demo/variants/{variant}.py", policy)
    # Synthetic failure-injection case, explicitly identified as such in its evidence.
    unknown = json.loads(json.dumps(reports["testable"]))
    unknown["measurements"]["correctness"] = {"status": "unknown", "reason": "Synthetic unavailable-check example"}
    reports["unknown-hard"] = unknown
    for name, report in reports.items():
        (args.output_dir / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cases = [
        ("baseline", "testable", "testability", "ACCEPT"),
        ("testable", "compact-regression", "source_lines", "REJECT"),
        ("testable", "efficient", "formatter_calls", "ACCEPT"),
        ("testable", "unknown-hard", "testability", "INCONCLUSIVE"),
    ]
    decisions = []
    for old, new, target, expected in cases:
        decision = evaluate(policy, reports[old], reports[new], target)
        if decision["status"] != expected:
            raise RuntimeError(f"{old} → {new}: expected {expected}, got {decision['status']}")
        decisions.append(dict(baseline=old, candidate=new, expected=expected, **decision))
        print(f"{old} → {new}: {decision['status']} — {decision['reason']}")
    (args.output_dir / "decisions.json").write_text(json.dumps(decisions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: four decisions checked, profile={args.profile}")


if __name__ == "__main__":
    main()
