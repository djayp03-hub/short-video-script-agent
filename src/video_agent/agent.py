import copy
import time

from .model_client import ModelError
from .schemas import ContractError, digest, error, ok, text, validate_draft, validate_request


class Agent:
    def __init__(self, model, tools, max_steps=12, max_seconds=240):
        if not isinstance(max_steps, int) or not 1 <= max_steps <= 50:
            raise ContractError("max_steps must be in [1, 50]")
        if not 0 < max_seconds <= 1800:
            raise ContractError("max_seconds must be in (0, 1800]")
        self.model, self.tools = model, tools
        self.max_steps, self.max_seconds = max_steps, max_seconds
        self.trace, self.revisions = [], []

    def run(self, request, initial_draft=None, require_revision=False):
        self.trace, self.revisions = [], []
        self.require_revision = require_revision and initial_draft is not None
        self.initial_draft_hash = None
        start = time.monotonic()
        state = {"request": copy.deepcopy(request), "evidence": {}, "draft": None,
                 "revision": 0, "checks": {}, "observations": []}
        self.state = state
        try:
            missing = validate_request(request)
            if missing:
                return self.result("needs_input", "missing_fields", missing_fields=missing,
                                   question="请补充：" + "、".join(missing))
            if initial_draft is not None:
                validate_draft(initial_draft)
                self.initial_draft_hash = digest(initial_draft)
                self.submit(initial_draft)
        except (ContractError, KeyError, TypeError) as exc:
            return self.result("failed", "invalid_input", detail=str(exc))
        for step in range(1, self.max_steps + 1):
            remaining = self.max_seconds - (time.monotonic() - start)
            if remaining <= 0:
                return self.result("incomplete", "time_limit")
            record = {"step": step, "mode": self.model.mode, "revision_before": state["revision"]}
            action = None
            self.trace.append(record)
            try:
                public = copy.deepcopy(state)
                public["remaining_steps"] = self.max_steps - step + 1
                public["brand_rules"] = self.tools.rules
                product = state["request"].get("product")
                product_ids = {m["id"] for m in self.tools.materials if m["product"] == product} if product else set()
                exhausted = bool(product_ids) and product_ids <= state["evidence"].keys()
                public["all_product_materials_retrieved"] = exhausted
                public["allowed_actions"] = ["submit_draft", "ask_user", "stop", "finish"]
                public["revision_required"] = self.revision_needed()
                if public["revision_required"]:
                    public["allowed_actions"].remove("finish")
                if not exhausted:
                    public["allowed_actions"].append("search_materials")
                if state["draft"]:
                    public["allowed_actions"] += [k for k in ("estimate_duration", "check_rules") if k not in state["checks"]]
                public["baseline_measurement_required"] = bool(initial_draft is not None and state["revision"] == 1 and "estimate_duration" not in state["checks"])
                if public["baseline_measurement_required"]:
                    public["allowed_actions"].remove("submit_draft")
                action = self.model.decide(public, timeout=remaining)
                record["decision"] = action
                if isinstance(action, dict) and action.get("action") not in public["allowed_actions"]:
                    raise ContractError("action unavailable: unchanged checks cannot improve; retrieved product corpus is exhausted. Choose from allowed_actions, modify the draft or stop.")
                if time.monotonic() - start >= self.max_seconds:
                    record["observation"] = error("time_limit", "模型返回时已达到总时间上限")
                    return self.result("incomplete", "time_limit")
                remaining = self.max_seconds - (time.monotonic() - start)
                observation, terminal = self.execute(action, remaining)
                record.update(observation=observation, revision_after=state["revision"],
                              elapsed_seconds=round(time.monotonic() - start, 3))
                state["observations"].append({"step": step, "decision": action, "observation": observation})
                if time.monotonic() - start >= self.max_seconds:
                    return self.result("incomplete", "time_limit")
                if terminal:
                    return terminal
            except ModelError as exc:
                observation = error(exc.code, "模型调用未成功；未切换为 Mock", exc.retryable)
                record["observation"] = observation
                if exc.code in {"invalid_model_json", "invalid_review_schema"}:
                    state["observations"].append({"step": step, "observation": observation})
                    continue
                return self.result("incomplete" if exc.code == "model_call_limit" else "failed", exc.code)
            except (ContractError, KeyError, TypeError) as exc:
                observation = error("invalid_action", str(exc))
                record["observation"] = observation
                state["observations"].append({"step": step, "decision": action, "observation": observation})
        return self.result("incomplete", "step_limit")

    def submit(self, draft):
        validate_draft(draft)
        if self.state['draft'] is not None and self.revision_needed() and digest(draft) == self.initial_draft_hash:
            raise ContractError('本轮要求改稿，不能重复提交未变化的上一版脚本')
        self.state["draft"] = copy.deepcopy(draft)
        self.state["revision"] += 1
        self.state["checks"] = {}
        self.revisions.append({"revision": self.state["revision"], "hash": digest(draft),
                               "draft": copy.deepcopy(draft)})

    def revision_needed(self):
        return bool(self.require_revision and digest(self.state['draft']) == self.initial_draft_hash)

    def fingerprint(self):
        return digest({"draft": self.state["draft"], "request": self.state["request"],
                       "materials": self.tools.material_hash, "rules": self.tools.rules_hash})

    def execute(self, decision, timeout):
        if not isinstance(decision, dict) or set(decision) != {"action", "args", "reason"}:
            raise ContractError("decision requires exactly TOP-LEVEL action, args, reason; reason must NOT be inside args")
        name, args = decision["action"], decision["args"]
        text(decision["reason"], "reason", 1500)
        required = {"search_materials": {"query"}, "submit_draft": {"draft"},
                    "estimate_duration": set(), "check_rules": set(), "finish": set(),
                    "ask_user": {"question"}, "stop": {"reason"}}
        if not isinstance(name, str) or name not in required or not isinstance(args, dict) or set(args) != required[name]:
            raise ContractError("unknown action or unexpected arguments")
        state = self.state
        if name in {"estimate_duration", "check_rules"}:
            # Invalidate any previous success before a new (possibly failed) check.
            state["checks"].pop(name, None)
        if name in {"search_materials", "estimate_duration", "check_rules"}:
            injected = self.tools.fault(name)
            if injected is not None:
                return injected, None
        if name == "search_materials":
            observation = self.tools.search(args["query"], state["request"].get("product"))
            for material in observation["data"]["materials"]:
                state["evidence"][material["id"]] = material
            return observation, None
        if name == "submit_draft":
            self.submit(args["draft"])
            return ok({"revision": state["revision"], "draft_hash": digest(state["draft"]),
                       "checks_invalidated": True}), None
        if name in {"estimate_duration", "check_rules"}:
            if state["draft"] is None:
                return error("no_draft", "请先提交脚本"), None
            if name == "estimate_duration":
                observation = self.tools.duration(state["draft"], state["request"]["target_seconds"])
            else:
                observation = self.tools.check(state["draft"], state["evidence"], self.model, timeout, state["request"])
            observation["data"].update(revision=state["revision"], fingerprint=self.fingerprint())
            state["checks"][name] = copy.deepcopy(observation["data"])
            return observation, None
        if name == "finish":
            checks = state["checks"]
            if self.revision_needed() or not state["draft"] or any(
                not checks.get(k, {}).get("passed") or checks[k].get("fingerprint") != self.fingerprint()
                for k in ("estimate_duration", "check_rules")):
                return error("finish_blocked", "当前脚本必须通过时长与规则检查；旧检查无效"), None
            return ok({"accepted": True}), self.result("completed", "checks_passed")
        if name == "ask_user":
            question = text(args["question"], "question")
            return ok({"question": question}), self.result("needs_input", "clarification", question=question)
        reason = text(args["reason"], "stop reason")
        return ok({"reason": reason}), self.result("incomplete", "model_stopped", detail=reason)

    def result(self, status, reason, **extra):
        state = self.state
        timing = state["checks"].get("estimate_duration", {})
        rule = state["checks"].get("check_rules", {})
        issues = list(rule.get("issues", []))
        if timing.get("passed") is False:
            issues.append("当前脚本预计时长超限")
        if status != "completed":
            issues.append("草稿未完成验收，不应作为已合格脚本使用")
        return {"status": status, "reason": reason, "mode": self.model.mode,
                "draft": copy.deepcopy(state["draft"]), "revision": state["revision"],
                "estimated_total_seconds": timing.get("total_seconds"),
                "checks": copy.deepcopy(state["checks"]), "sources": copy.deepcopy(list(state["evidence"].values())),
                "risks": issues, "human_review": "pending", "steps": len(self.trace), **extra}
