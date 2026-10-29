import copy
import re
from collections import Counter

from .schemas import ContractError, digest, error, number, ok, text


def tokens(value):
    value = value.lower()
    words = re.findall(r"[a-z0-9]+", value)
    for part in re.findall(r"[\u4e00-\u9fff]+", value):
        words.extend(part[i:i + 2] for i in range(max(1, len(part) - 1)))
    return set(words)


class ToolBox:
    def __init__(self, materials, rules, faults=None):
        if not isinstance(rules, list):
            raise ContractError("rules must be a JSON array")
        rule_ids = set()
        for rule in rules:
            if not isinstance(rule, dict):
                raise ContractError("each rule must be an object")
            for field in ("id", "description"):
                text(rule.get(field), "rule." + field, 5000)
            if rule["id"] in rule_ids:
                raise ContractError("duplicate rule IDs")
            rule_ids.add(rule["id"])
            for field in ("forbidden_phrases", "detail_terms"):
                values = rule.get(field, [])
                if not isinstance(values, list):
                    raise ContractError("rule." + field + " must be an array")
                for value in values:
                    text(value, "rule." + field, 500)
        self.materials = copy.deepcopy(materials)
        self.rules = copy.deepcopy(rules)
        ids = [m["id"] for m in materials]
        if len(ids) != len(set(ids)):
            raise ContractError("duplicate material IDs")
        for m in materials:
            for k in ("id", "product", "version", "text"):
                text(m[k], k, 10000)
        self.faults = faults or {}
        if set(self.faults) - {"search_materials", "estimate_duration", "check_rules"}:
            raise ContractError("unknown fault tool")
        for value in self.faults.values():
            if value not in {"once", "always", "empty_once", "empty_always"}:
                raise ContractError("unknown fault mode")
        self.counts = Counter()
        self.material_hash = digest(materials)
        self.rules_hash = digest(rules)

    def fault(self, name):
        self.counts[name] += 1
        mode = self.faults.get(name)
        active = mode in {"always", "empty_always"} or (mode in {"once", "empty_once"} and self.counts[name] == 1)
        if not active:
            return None
        if mode.startswith("empty") and name == "search_materials":
            return ok({"materials": [], "injected": True})
        return error("injected_timeout", "故障注入：模拟工具超时", True)

    def search(self, query, product=None):
        query = text(query, "query", 500)
        scored = []
        for m in self.materials:
            if product and m["product"] != product:
                continue
            hay = " ".join([m["product"], m["text"], *m.get("keywords", [])])
            score = len(tokens(query) & tokens(hay))
            if score:
                scored.append((score, m))
        scored.sort(key=lambda item: (-item[0], item[1]["id"]))
        return ok({"materials": [m for _, m in scored[:5]], "query": query})

    def duration(self, draft, target):
        timings = []
        for index, scene in enumerate(draft["scenes"], 1):
            def seconds(value, zh_rate, en_rate):
                chinese = len(re.findall(r"[\u4e00-\u9fff]", value))
                english = len(re.findall(r"[A-Za-z0-9]+", value))
                pauses = len(re.findall(r"[，。！？；,.!?;]", value)) * 0.15
                return chinese / zh_rate + english / en_rate + pauses
            voice = seconds(scene["narration"], 4.0, 2.5)
            subtitle = seconds(scene["subtitle"], 5.0, 3.0)
            length = round(max(voice, subtitle, scene["min_seconds"]), 2)
            timings.append({"scene": index, "seconds": length,
                            "voice_seconds": round(voice, 2), "subtitle_seconds": round(subtitle, 2)})
        total = round(sum(t["seconds"] for t in timings) + max(0, len(timings) - 1) * 0.25, 2)
        return ok({"passed": total <= target, "total_seconds": total, "target_seconds": target,
                   "excess_seconds": round(max(0, total - target), 2), "scenes": timings,
                   "assumptions": {"zh_voice_chars_per_second": 4, "zh_subtitle_chars_per_second": 5,
                    "en_voice_words_per_second": 2.5, "en_subtitle_words_per_second": 3,
                    "punctuation_pause_seconds": 0.15, "transition_seconds": 0.25,
                    "parallel_tracks": "max(voice, subtitle, min_seconds)", "kind": "estimate_not_recorded_audio"}})

    def check(self, draft, evidence, model, timeout, request=None):
        issues = []
        visible = draft["title"] + "\n" + "\n".join(
            s[k] for s in draft["scenes"] for k in ("visual", "narration", "subtitle"))
        for rule in self.rules:
            for banned in rule.get("forbidden_phrases", []):
                if banned in visible:
                    issues.append(f"{rule['id']}: 出现禁用表达 {banned}")
            # Conservative lexical guard for observed semantic-review false negatives.
            title_evidence = "\n".join(m["text"] for m in evidence.values())
            for term in rule.get("detail_terms", []):
                if term in draft["title"] and term not in title_evidence:
                    issues.append(f"{rule['id']}: title 无依据的具体细节：{term}")
                for i, scene in enumerate(draft["scenes"], 1):
                    scene_text = "\n".join(scene[k] for k in ("visual", "narration", "subtitle"))
                    sources = "\n".join(evidence[k]["text"] for k in scene["source_ids"] if k in evidence)
                    if term in scene_text and term not in sources:
                        issues.append(f"{rule['id']}: scene {i} 无依据的具体细节：{term}")
        for i, scene in enumerate(draft["scenes"], 1):
            for source in scene["source_ids"]:
                if source not in evidence:
                    issues.append(f"scene {i}: 未检索到引用 {source}")
        if issues:
            return ok({"passed": False, "issues": issues, "review_mode": "mechanical"})
        review = model.review(draft, list(evidence.values()), self.rules, timeout, request=request)
        return ok({"passed": review["supported"] and not review["issues"],
                   "issues": review["issues"], "review_mode": model.mode,
                   "semantic_supported": review["supported"],
                   "limitation": "自动审核不是独立人工事实复核"})
