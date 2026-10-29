"""Deterministic simulation ONLY. Never use these traces as model decision evidence."""
from .schemas import digest


class MockModel:
    mode = "mock"
    model = "deterministic-offline-simulator-v1"

    def __init__(self):
        self.calls = []

    def decide(self, state, timeout=None):
        def action(name, args, why):
            return {"action": name, "args": args, "reason": "[MOCK 固定规则] " + why}
        observations = state["observations"]
        if observations and not observations[-1]["observation"]["ok"]:
            last = observations[-1]
            if len(observations) > 1 and not observations[-2]["observation"]["ok"]:
                return action("stop", {"reason": "工具连续失败"}, "离线错误分支")
            if "decision" in last:
                return last["decision"]
        request = state["request"]
        if not state["evidence"]:
            searches = sum(o.get("decision", {}).get("action") == "search_materials" for o in observations)
            if searches >= 2:
                return action("ask_user", {"question": "请提供该主题的产品素材"}, "没有证据")
            return action("search_materials", {"query": request.get("product", request["theme"])}, "查找素材")
        if state["draft"] is None:
            materials = list(state["evidence"].values())[:2]
            scenes = [{"visual": "展示素材原文卡片", "narration": m["text"], "subtitle": "",
                       "source_ids": [m["id"]], "min_seconds": 2} for m in materials]
            return action("submit_draft", {"draft": {"title": request["theme"], "scenes": scenes}}, "离线原文拼接")
        checks = state["checks"]
        if "estimate_duration" not in checks:
            return action("estimate_duration", {}, "检查时长")
        if not checks["estimate_duration"]["passed"]:
            material = next(iter(state["evidence"].values()))
            sentence = material["text"].split("。")[0] + "。"
            draft = {"title": request["theme"], "scenes": [{"visual": "展示素材原文卡片",
                     "narration": sentence, "subtitle": "", "source_ids": [material["id"]], "min_seconds": 1}]}
            if digest(draft) == digest(state["draft"]):
                return action("stop", {"reason": "最短原文仍超时长"}, "离线失败分支")
            return action("submit_draft", {"draft": draft}, "离线取第一句压缩")
        if "check_rules" not in checks:
            return action("check_rules", {}, "检查规则")
        if not checks["check_rules"]["passed"]:
            return action("stop", {"reason": "离线规则检查未通过"}, "离线不实现创作修复")
        return action("finish", {}, "两项检查完成")

    def review(self, draft, evidence, rules, timeout=None, request=None):
        lookup = {m["id"]: m for m in evidence}
        issues = []
        for i, s in enumerate(draft["scenes"], 1):
            corpus = "\n".join(lookup[k]["text"] for k in s["source_ids"])
            for key in ("narration", "subtitle"):
                if s[key] and s[key] not in corpus:
                    issues.append(f"scene {i}: Mock 只接受素材原文，不能判定改写语义")
        return {"supported": not issues, "issues": issues}
