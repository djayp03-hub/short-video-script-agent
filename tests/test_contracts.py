import copy
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from video_agent.agent import Agent
from video_agent.cli import execute_run, read
from video_agent.mock_model import MockModel
from video_agent.model_client import ModelError, normalize_decision, parse_json
from video_agent.schemas import ContractError, digest, validate_draft, validate_request
from video_agent.tools import ToolBox


def action(name, **args):
    return {"action": name, "args": args, "reason": "测试输入，不是真实模型决策"}


class SequenceModel(MockModel):
    def __init__(self, sequence):
        super().__init__()
        self.sequence = iter(sequence)
        self.observed_states = []

    def decide(self, state, timeout=None):
        self.observed_states.append(copy.deepcopy(state))
        return next(self.sequence, action("finish"))


class Contracts(unittest.TestCase):
    def setUp(self):
        self.request = read(ROOT / "data/request.json")
        self.materials = read(ROOT / "data/materials.json")
        self.rules = read(ROOT / "data/brand_rules.json")
        self.draft = {"title": "字幕操作", "scenes": [{"visual": "展示资料卡片",
            "narration": "剪映盒演示版支持手动添加字幕。", "subtitle": "", "source_ids": ["P01"], "min_seconds": 2}]}

    def agent(self, sequence, **kwargs):
        return Agent(SequenceModel(sequence), ToolBox(self.materials, self.rules), **kwargs)

    def prefix(self):
        return [action("search_materials", query="字幕"), action("submit_draft", draft=self.draft)]

    def checked(self):
        return self.prefix() + [action("estimate_duration"), action("check_rules")]

    def test_missing_fields_requests_input_without_model_calls(self):
        del self.request["target_seconds"]
        a = self.agent([])
        self.assertEqual(a.run(self.request)["status"], "needs_input")
        self.assertEqual(a.trace, [])

    def test_nonfinite_or_boolean_target_rejected(self):
        for value in [True, math.inf, math.nan, 0, -1, "30"]:
            with self.subTest(value=value):
                with self.assertRaises(ContractError):
                    validate_request(dict(self.request, target_seconds=value))

    def test_draft_contract_rejects_nan_and_extra_fields(self):
        d = copy.deepcopy(self.draft)
        d["scenes"][0]["min_seconds"] = math.nan
        with self.assertRaises(ContractError):
            validate_draft(d)
        with self.assertRaises(ContractError):
            validate_draft(dict(self.draft, passed=True))

    def test_finish_without_checks_blocked(self):
        a = self.agent([action("finish")], max_steps=1)
        result = a.run(self.request)
        self.assertEqual(result["reason"], "step_limit")
        self.assertEqual(a.trace[0]["observation"]["error"]["code"], "finish_blocked")

    def test_only_current_checked_draft_can_finish(self):
        a = self.agent(self.checked() + [action("finish")])
        result = a.run(self.request)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["checks"]["check_rules"]["revision"], 1)

    def test_edit_invalidates_checks(self):
        changed = copy.deepcopy(self.draft)
        changed["title"] = "新的标题"
        a = self.agent(self.checked() + [action("submit_draft", draft=changed), action("finish")], max_steps=6)
        result = a.run(self.request)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["checks"], {})
        self.assertEqual(len(a.revisions), 2)

    def test_conversation_revision_cannot_finish_with_the_unchanged_old_draft(self):
        sequence = [action('search_materials', query='字幕'), action('estimate_duration'),
                    action('check_rules'), action('finish')]
        agent = self.agent(sequence, max_steps=4)
        result = agent.run(self.request, self.draft, require_revision=True)
        self.assertNotEqual(result['status'], 'completed')
        self.assertTrue(agent.model.observed_states[-1]['revision_required'])
        self.assertNotIn('finish', agent.model.observed_states[-1]['allowed_actions'])

    def test_conversation_revision_can_finish_after_changed_draft_and_fresh_checks(self):
        changed = copy.deepcopy(self.draft)
        changed['title'] = '手动字幕介绍'
        sequence = [action('search_materials', query='字幕'), action('estimate_duration'),
                    action('submit_draft', draft=changed), action('estimate_duration'),
                    action('check_rules'), action('finish')]
        agent = self.agent(sequence)
        result = agent.run(self.request, self.draft, require_revision=True)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['checks']['check_rules']['revision'], 2)

    def test_invalid_initial_draft_fails_before_revision_hashing(self):
        invalid = copy.deepcopy(self.draft)
        invalid['scenes'][0]['min_seconds'] = math.nan
        result = self.agent([]).run(self.request, invalid, require_revision=True)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['reason'], 'invalid_input')

    def test_new_failed_check_invalidates_previous_success(self):
        a = self.agent(self.checked())
        a.run(self.request)
        a.tools.faults["check_rules"] = "always"
        observation, _ = a.execute(action("check_rules"), 10)
        self.assertFalse(observation["ok"])
        observation, terminal = a.execute(action("finish"), 10)
        self.assertIsNone(terminal)
        self.assertEqual(observation["error"]["code"], "finish_blocked")

    def test_unknown_source_not_accepted(self):
        self.draft["scenes"][0]["source_ids"] = ["invented"]
        a = self.agent(self.checked(), max_steps=5)
        result = a.run(self.request)
        self.assertFalse(result["checks"]["check_rules"]["passed"])
        self.assertNotEqual(result["status"], "completed")

    def test_banned_claim_in_title_is_rejected(self):
        self.draft["title"] = "保证爆款"
        a = self.agent(self.checked(), max_steps=5)
        result = a.run(self.request)
        self.assertFalse(result["checks"]["check_rules"]["passed"])

    def test_real_failure_regression_unsupported_ui_is_blocked(self):
        self.draft["scenes"][0]["visual"] = "点击手机左下角的保存草稿按钮"
        a = self.agent(self.checked(), max_steps=5)
        result = a.run(self.request)
        self.assertNotEqual(result["status"], "completed")
        self.assertTrue(any("无依据" in i for i in result["checks"]["check_rules"]["issues"]))

    def test_abstract_scene_without_product_interface_is_allowed(self):
        self.draft["scenes"][0]["visual"] = "纯色块示意（无任何设备、图标或文字）"
        a = self.agent(self.checked() + [action("finish")])
        self.assertEqual(a.run(self.request)["status"], "completed")

    def test_title_speed_claim_is_blocked(self):
        self.draft["title"] = "学生党30秒上手"
        a = self.agent(self.checked(), max_steps=5)
        self.assertFalse(a.run(self.request)["checks"]["check_rules"]["passed"])

    def test_tool_observation_reaches_next_model_turn(self):
        a = self.agent(self.checked(), max_steps=4)
        a.run(self.request)
        state = a.model.observed_states[1]
        self.assertIn("P01", state["evidence"])
        self.assertEqual(state["observations"][0]["decision"]["action"], "search_materials")

    def test_model_is_told_not_to_reestimate_unchanged_draft(self):
        a = self.agent(self.prefix() + [action("estimate_duration"), action("stop", reason="done")])
        a.run(dict(self.request, target_seconds=1))
        latest = a.model.observed_states[-1]
        self.assertFalse(latest["checks"]["estimate_duration"]["passed"])
        self.assertNotIn("estimate_duration", latest["allowed_actions"])
        self.assertIn("submit_draft", latest["allowed_actions"])

    def test_model_is_told_when_product_corpus_is_exhausted(self):
        a = self.agent([action("search_materials", query="剪映盒演示版"), action("stop", reason="done")])
        a.run(self.request)
        latest = a.model.observed_states[-1]
        self.assertNotIn("search_materials", latest["allowed_actions"])
        self.assertTrue(latest["all_product_materials_retrieved"])

    def test_tool_failure_is_distinct_from_empty_results(self):
        tools = ToolBox(self.materials, self.rules, {"search_materials": "once"})
        self.assertFalse(tools.fault("search_materials")["ok"])
        self.assertIsNone(tools.fault("search_materials"))
        empty = tools.search("zzyyunknown")
        self.assertTrue(empty["ok"])
        self.assertEqual(empty["data"]["materials"], [])

    def test_product_filter_excludes_other_edition(self):
        found = ToolBox(self.materials, self.rules).search("自动字幕", "剪映盒演示版")
        self.assertNotIn("D01", [m["id"] for m in found["data"]["materials"]])

    def test_timing_parallel_tracks_not_double_counted(self):
        self.draft["scenes"][0].update(narration="一二三四五六七八", subtitle="一二三四五六七八", min_seconds=1)
        timing = ToolBox(self.materials, self.rules).duration(self.draft, 3)["data"]
        self.assertEqual(timing["total_seconds"], 2)
        self.assertTrue(timing["passed"])

    def test_timing_transition_sum(self):
        self.draft["scenes"] *= 2
        timing = ToolBox(self.materials, self.rules).duration(self.draft, 30)["data"]
        self.assertEqual(timing["total_seconds"], round(sum(x["seconds"] for x in timing["scenes"]) + .25, 2))

    def test_overlong_cannot_finish(self):
        a = self.agent(self.checked() + [action("finish")], max_steps=5)
        result = a.run(dict(self.request, target_seconds=1))
        self.assertEqual(result["status"], "incomplete")
        self.assertFalse(result["checks"]["estimate_duration"]["passed"])

    def test_invalid_action_consumes_budget(self):
        a = self.agent([action("publish_to_platform")], max_steps=1)
        result = a.run(self.request)
        self.assertEqual(result["reason"], "step_limit")
        self.assertEqual(result["steps"], 1)

    def test_model_error_never_falls_back_to_mock(self):
        class Broken(SequenceModel):
            mode = "real"
            def decide(self, state, timeout=None):
                raise ModelError("http_401")
        a = Agent(Broken([]), ToolBox(self.materials, self.rules))
        result = a.run(self.request)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["mode"], "real")

    def test_parser_rejects_unstructured_and_arrays(self):
        for raw in ["I finished", "[]", "{broken}"]:
            with self.assertRaises(ModelError):
                parse_json(raw)
        self.assertEqual(parse_json('```json\n{"a":1}\n```'), {"a": 1})

    def test_null_provider_content_is_a_controlled_error(self):
        with self.assertRaises(ModelError):
            parse_json(None)

    def test_initial_fixture_must_be_measured_before_replacement(self):
        a = self.agent([action("search_materials", query="字幕"),
                        action("submit_draft", draft=self.draft)], max_steps=2)
        a.run(self.request, initial_draft=self.draft)
        self.assertNotIn("submit_draft", a.model.observed_states[1]["allowed_actions"])

    def test_adapter_only_moves_reason_preserving_raw_response(self):
        raw = {"action": "submit_draft", "args": {"draft": self.draft, "reason": "证据依据"}}
        original = copy.deepcopy(raw)
        normalized = normalize_decision(raw)
        self.assertEqual(raw, original)
        self.assertEqual(normalized, action("submit_draft", draft=self.draft) | {"reason": "证据依据"})
        malformed = {"action": "invented"}
        self.assertEqual(normalize_decision(malformed), malformed)

    def test_repeated_run_does_not_reuse_evidence(self):
        a = Agent(MockModel(), ToolBox(self.materials, self.rules))
        self.assertEqual(a.run(self.request)["status"], "completed")
        second = a.run(dict(self.request, product="未知产品"))
        self.assertNotEqual(second["status"], "completed")
        self.assertEqual(second["sources"], [])

    def test_artifacts_are_real_outputs_and_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run"
            result = execute_run(self.request, self.materials, self.rules, path)
            self.assertEqual(read(path / "output.json"), result)
            self.assertTrue((path / "trace.jsonl").stat().st_size)
            self.assertEqual(read(path / "run.json")["mode"], "mock")
            with self.assertRaises(FileExistsError):
                execute_run(self.request, self.materials, self.rules, path)

    def test_hash_changes_with_content(self):
        self.assertNotEqual(digest(self.draft), digest(dict(self.draft, title="changed")))

    def test_duplicate_material_id_rejected(self):
        with self.assertRaises(ContractError):
            ToolBox(self.materials + [self.materials[0]], self.rules)

    def test_invalid_rule_structure_is_rejected(self):
        for rules in [{}, ["bad rule"], [{"id": "R01", "description": "policy", "forbidden_phrases": "bad"}]]:
            with self.subTest(rules=rules):
                with self.assertRaises(ContractError):
                    ToolBox(self.materials, rules)

    def test_invalid_rules_still_produce_terminal_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "run"
            result = execute_run(self.request, self.materials, ["bad rule"], path)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(read(path / "output.json")["status"], "failed")
            self.assertTrue((path / "trace.jsonl").exists())
            self.assertTrue((path / "run.json").exists())


if __name__ == "__main__":
    unittest.main()
