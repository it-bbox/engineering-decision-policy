#!/usr/bin/env python3
"""Compare collected evidence. Python 3.10+, standard library only."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_policy(policy):
    if not isinstance(policy, dict):
        raise ValueError("Policy must be a JSON object")
    if policy.get("schema_version") != 2:
        raise ValueError("Policy schema_version must be 2")
    for field in ("profile", "scope", "suite_id"):
        if not isinstance(policy.get(field), str) or not policy[field].strip():
            raise ValueError(f"Missing policy field: {field}")
    if not isinstance(policy.get("hard_constraints"), list) or not policy["hard_constraints"]:
        raise ValueError("At least one hard constraint is required")
    if not isinstance(policy.get("levels"), list) or not policy["levels"]:
        raise ValueError("At least one ordered level is required")
    seen = set()
    for item in policy["hard_constraints"] + policy["levels"]:
        if not isinstance(item, dict):
            raise ValueError("Policy entries must be JSON objects")
        key = item.get("id")
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError("Constraint and level IDs must be unique nonempty strings")
        seen.add(key)
        for field in ("label", "method", "limitation", "unit"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(f"{key}: missing {field}")
        if item.get("evidence_kind") not in ("direct", "scenario", "proxy"):
            raise ValueError(f"{key}: invalid evidence_kind")
        if item.get("type") not in ("binary", "number"):
            raise ValueError(f"{key}: invalid type")
        if item["type"] == "binary":
            if item.get("gate") is not True or item.get("direction") != "max":
                raise ValueError(f"{key}: binary requires gate=true and direction=max")
        else:
            if item.get("direction") not in ("min", "max") or not number(item.get("gate")):
                raise ValueError(f"{key}: numeric direction/gate invalid")
            delta = item.get("min_improvement", 0)
            if not number(delta) or delta < 0:
                raise ValueError(f"{key}: min_improvement must be finite and nonnegative")
    budget = policy.get("search_budget", {})
    if not isinstance(budget, dict):
        raise ValueError("search_budget must be a JSON object")
    for key in ("max_attempts_per_level", "max_total_minutes"):
        if type(budget.get(key)) is not int or budget[key] <= 0:
            raise ValueError(f"search_budget.{key} must be a positive integer")


def value_of(report, metric):
    entry = report.get("measurements", {}).get(metric["id"])
    if entry is None:
        return None
    if not isinstance(entry, dict) or entry.get("status") not in ("measured", "unknown"):
        raise ValueError(f"{metric['id']}: invalid measurement status")
    if entry["status"] == "unknown":
        if not isinstance(entry.get("reason"), str) or not entry["reason"].strip():
            raise ValueError(f"{metric['id']}: unknown requires reason")
        return None
    value = entry.get("value")
    valid = type(value) is bool if metric["type"] == "binary" else number(value)
    if not valid:
        raise ValueError(f"{metric['id']}: wrong measurement type or nonfinite number")
    if not isinstance(entry.get("evidence"), str) or not entry["evidence"].strip():
        raise ValueError(f"{metric['id']}: measured requires evidence")
    return value


def gate(metric, value):
    if value is None:
        return None
    if metric["type"] == "binary":
        return value is True
    return value >= metric["gate"] if metric["direction"] == "max" else value <= metric["gate"]


def gain(metric, old, new):
    delta = int(new) - int(old) if metric["type"] == "binary" else new - old
    return delta if metric["direction"] == "max" else -delta


def validate_report(policy, report):
    if not isinstance(report, dict):
        raise ValueError("Report must be a JSON object")
    if report.get("schema_version") != 2 or not isinstance(report.get("measurements"), dict):
        raise ValueError("Report schema/measurements invalid")
    expected = {"policy_sha256": digest(policy), "scope": policy["scope"], "suite_id": policy["suite_id"]}
    for key, value in expected.items():
        if report.get(key) != value:
            raise ValueError(f"Report {key} does not match policy")
    for key in ("source_revision", "environment", "experiment_id", "collected_at"):
        if not isinstance(report.get(key), str) or not report[key].strip():
            raise ValueError(f"Report missing {key}")
    metrics = policy["hard_constraints"] + policy["levels"]
    if set(report["measurements"]) - {m["id"] for m in metrics}:
        raise ValueError("Report contains unconfigured measurements")
    for metric in metrics:
        value_of(report, metric)


def evaluate(policy, baseline, candidate, target):
    validate_policy(policy)
    validate_report(policy, baseline)
    validate_report(policy, candidate)
    for key in ("environment", "experiment_id"):
        if baseline[key] != candidate[key]:
            raise ValueError(f"Incomparable reports: different {key}")
    levels = policy["levels"]
    ids = [m["id"] for m in levels]
    if target not in ids:
        raise ValueError(f"Unknown target: {target}")
    index = ids.index(target)
    rows = []
    for metric in policy["hard_constraints"] + levels:
        old, new = value_of(baseline, metric), value_of(candidate, metric)
        rows.append({"id": metric["id"], "baseline": old, "candidate": new,
                     "candidate_gate": gate(metric, new), "evidence_kind": metric["evidence_kind"]})
    unresolved = [r["id"] for r in rows if r["candidate_gate"] is not True]

    def result(status, reason):
        return {"schema_version": 2, "status": status, "reason": reason, "target": target,
                "next_level_allowed": status in ("ACCEPT", "NO_CHANGE") and all(
                    gate(m, value_of(candidate, m)) is True for m in levels[:index + 1]),
                "unresolved": unresolved, "all_configured_gates_met": not unresolved,
                "global_optimum_proven": False, "measurements": rows}

    for metric in policy["hard_constraints"]:
        old, new = value_of(baseline, metric), value_of(candidate, metric)
        if gate(metric, new) is False:
            return result("REJECT", f"Hard constraint failed: {metric['id']}")
        if new is None:
            return result("INCONCLUSIVE", f"Hard constraint unknown: {metric['id']}")
        if gate(metric, old) is not True:
            return result("BASELINE_INVALID", f"Repair baseline first: {metric['id']}")
    for metric in levels[:index]:
        old, new = value_of(baseline, metric), value_of(candidate, metric)
        if old is None or new is None:
            return result("INCONCLUSIVE", f"Previous level unknown: {metric['id']}")
        if gate(metric, old) is not True:
            return result("BASELINE_INVALID", f"Previous gate not reached: {metric['id']}")
        if gate(metric, new) is not True or gain(metric, old, new) < 0:
            return result("REJECT", f"Previous level regressed: {metric['id']}")
    metric = levels[index]
    old, new = value_of(baseline, metric), value_of(candidate, metric)
    if old is None or new is None:
        return result("INCONCLUSIVE", f"Target unknown: {target}")
    delta = gain(metric, old, new)
    if delta < 0:
        return result("REJECT", f"Target regressed: {target}")
    if delta <= metric.get("min_improvement", 0):
        return result("NO_CHANGE", "No improvement above min_improvement; checkpoint stays unchanged")
    if gate(metric, new) is not True:
        return result("ACCEPT_PROGRESS", "Improved, but target gate is not reached; stay at this level")
    return result("ACCEPT", "Target improved; hard constraints and all previous levels preserved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        decision = evaluate(read_json(args.policy), read_json(args.baseline), read_json(args.candidate), args.target)
    except (ValueError, TypeError, KeyError, OSError) as error:
        decision = {"status": "INVALID", "reason": str(error), "next_level_allowed": False}
    rendered = json.dumps(decision, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return {"ACCEPT": 0, "ACCEPT_PROGRESS": 10, "NO_CHANGE": 11, "REJECT": 20,
            "INCONCLUSIVE": 21, "BASELINE_INVALID": 22, "INVALID": 23}[decision["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
