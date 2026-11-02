"""Behavioral tests for the policy comparator, including bypass attempts."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate import digest, evaluate, read_json
from run_demo import collect


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = read_json(ROOT / "configs/production.json")
        self.baseline = collect(ROOT / "demo/variants/testable.py", self.policy)
        self.candidate = collect(ROOT / "demo/variants/efficient.py", self.policy)

    def decide(self, target="formatter_calls"):
        return evaluate(self.policy, self.baseline, self.candidate, target)

    def set_value(self, report, key, value):
        report["measurements"][key]["value"] = value

    def rebind(self):
        for report in (self.baseline, self.candidate):
            report["policy_sha256"] = digest(self.policy)

    def test_real_work_improvement(self):
        result = self.decide()
        self.assertEqual(result["status"], "ACCEPT")
        self.assertTrue(result["all_configured_gates_met"])
        self.assertFalse(result["global_optimum_proven"])

    def test_nonadjacent_prior_regression_is_rejected(self):
        self.set_value(self.candidate, "testability", False)
        self.assertEqual(self.decide()["status"], "REJECT")

    def test_numeric_regression_rejected_even_if_gate_still_passes(self):
        self.set_value(self.candidate, "source_lines", 49)
        self.assertEqual(self.decide()["status"], "REJECT")

    def test_lower_gain_cannot_buy_hard_failure(self):
        self.set_value(self.candidate, "correctness", False)
        self.assertEqual(self.decide()["status"], "REJECT")

    def test_unknown_hard_cannot_pass(self):
        self.candidate["measurements"]["correctness"] = {"status": "unknown", "reason": "unavailable"}
        self.assertEqual(self.decide()["status"], "INCONCLUSIVE")

    def test_missing_prior_cannot_pass(self):
        del self.candidate["measurements"]["extensibility"]
        self.assertEqual(self.decide()["status"], "INCONCLUSIVE")

    def test_missing_target_cannot_pass(self):
        del self.candidate["measurements"]["formatter_calls"]
        self.assertEqual(self.decide()["status"], "INCONCLUSIVE")

    def test_invalid_baseline_is_not_optimization(self):
        self.set_value(self.baseline, "correctness", False)
        self.assertEqual(self.decide()["status"], "BASELINE_INVALID")

    def test_cannot_skip_unreached_gate(self):
        self.set_value(self.baseline, "extensibility", False)
        self.assertEqual(self.decide()["status"], "BASELINE_INVALID")

    def test_progress_without_gate_stays_at_level(self):
        self.set_value(self.baseline, "source_lines", 80)
        self.set_value(self.candidate, "source_lines", 60)
        result = self.decide("source_lines")
        self.assertEqual(result["status"], "ACCEPT_PROGRESS")
        self.assertFalse(result["next_level_allowed"])

    def test_equal_target_keeps_checkpoint(self):
        self.candidate = copy.deepcopy(self.baseline)
        result = self.decide()
        self.assertEqual(result["status"], "NO_CHANGE")
        self.assertTrue(result["next_level_allowed"])

    def test_no_change_below_gate_cannot_advance(self):
        self.set_value(self.baseline, "formatter_calls", 10)
        self.set_value(self.candidate, "formatter_calls", 10)
        result = self.decide()
        self.assertEqual(result["status"], "NO_CHANGE")
        self.assertFalse(result["next_level_allowed"])

    def test_gate_is_inclusive(self):
        self.set_value(self.candidate, "source_lines", 50)
        self.set_value(self.baseline, "source_lines", 60)
        self.assertEqual(self.decide("source_lines")["status"], "ACCEPT")

    def test_min_improvement_is_strict_and_does_not_allow_regression(self):
        self.policy["levels"][-1]["min_improvement"] = 3
        self.rebind()
        self.assertEqual(self.decide()["status"], "NO_CHANGE")
        self.set_value(self.candidate, "formatter_calls", 7)
        self.assertEqual(self.decide()["status"], "REJECT")

    def test_numeric_max_direction(self):
        self.policy["levels"][-1].update(direction="max", gate=8)
        self.set_value(self.candidate, "formatter_calls", 9)
        self.rebind()
        self.assertEqual(self.decide()["status"], "ACCEPT")

    def test_unknown_lower_level_does_not_block_early_gain(self):
        self.set_value(self.baseline, "testability", False)
        del self.candidate["measurements"]["formatter_calls"]
        result = self.decide("testability")
        self.assertEqual(result["status"], "ACCEPT")
        self.assertFalse(result["all_configured_gates_met"])

    def test_policy_hash_change_requires_new_reports(self):
        self.policy["profile"] = "changed"
        with self.assertRaises(ValueError):
            self.decide()

    def test_report_pair_must_be_comparable(self):
        for key in ("scope", "suite_id", "environment", "experiment_id"):
            with self.subTest(key=key):
                candidate = copy.deepcopy(self.candidate)
                candidate[key] = "different"
                with self.assertRaises(ValueError):
                    evaluate(self.policy, self.baseline, candidate, "formatter_calls")

    def test_invalid_values_are_not_success(self):
        for value in (True, "3", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.set_value(self.candidate, "formatter_calls", value)
                with self.assertRaises(ValueError):
                    self.decide()

    def test_binary_rejects_number(self):
        self.set_value(self.candidate, "testability", 1)
        with self.assertRaises(ValueError):
            self.decide()

    def test_measured_requires_evidence(self):
        self.candidate["measurements"]["testability"]["evidence"] = ""
        with self.assertRaises(ValueError):
            self.decide()

    def test_duplicate_ids_are_invalid(self):
        self.policy["levels"][1]["id"] = "testability"
        self.rebind()
        with self.assertRaises(ValueError):
            self.decide()

    def test_nonobject_inputs_are_invalid(self):
        with self.assertRaises(ValueError):
            evaluate([], self.baseline, self.candidate, "formatter_calls")
        with self.assertRaises(ValueError):
            evaluate(self.policy, self.baseline, [], "formatter_calls")

    def test_duplicate_json_keys_are_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"value": false, "value": true}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_json(path)

    def test_profile_order_is_used(self):
        self.policy = read_json(ROOT / "configs/realtime.json")
        self.rebind()
        self.set_value(self.candidate, "testability", False)
        result = self.decide()
        self.assertEqual(result["status"], "ACCEPT")
        self.assertFalse(result["all_configured_gates_met"])


if __name__ == "__main__":
    unittest.main()
