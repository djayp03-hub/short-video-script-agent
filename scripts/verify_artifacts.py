"""Independent evidence audit; reads saved runs, never invokes the Agent/model."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def hash_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def verify(folder):
    errors = []
    required = ["input.json", "output.json", "materials.json", "rules.json", "run.json",
                "trace.jsonl", "model-calls.json", "revisions.json"]
    for name in required:
        if not (folder / name).exists():
            errors.append("missing:" + name)
    if errors:
        return errors
    run, output = read(folder / "run.json"), read(folder / "output.json")
    request, materials, rules = [read(folder / n) for n in ["input.json", "materials.json", "rules.json"]]
    for key, value in [("input_hash", request), ("materials_hash", materials), ("rules_hash", rules)]:
        if run[key] != hash_json(value):
            errors.append("hash_mismatch:" + key)
    trace = [json.loads(line) for line in (folder / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(trace) != output["steps"] or len(trace) > run["max_steps"]:
        errors.append("step_count_mismatch")
    calls = read(folder / "model-calls.json")
    if run["mode"] != output["mode"] or run["model_calls"] != len(calls):
        errors.append("mode_or_calls_mismatch")
    retrieved = {}
    for row in trace:
        obs = row.get("observation", {})
        if row.get("decision", {}).get("action") == "search_materials" and obs.get("ok"):
            for material in obs.get("data", {}).get("materials", []):
                retrieved[material["id"]] = material
    if {m["id"]: m for m in output.get("sources", [])} != retrieved:
        errors.append("sources_not_in_search_observations")
    if run["mode"] == "real":
        decisions = []
        for call in calls:
            if call.get("purpose") == "decision" and "response" in call:
                raw = call["response"]
                if call.get("adapter_normalization") == "moved_reason_from_args_to_top_level":
                    raw = {"action": raw["action"], "args": {k:v for k,v in raw["args"].items() if k != "reason"}, "reason": raw["args"]["reason"]}
                decisions.append(raw)
        if decisions != [r["decision"] for r in trace if "decision" in r]:
            errors.append("model_decisions_do_not_match_trace")
        reviews = [c["response"] for c in calls if c.get("purpose") == "grounding_review" and "response" in c]
        observed_reviews = [r["observation"]["data"] for r in trace if r.get("decision", {}).get("action") == "check_rules" and (r.get("observation", {}).get("data") or {}).get("review_mode") == "real"]
        if len(reviews) != len(observed_reviews) or any(a.get("supported") != b.get("semantic_supported") or a.get("issues") != b.get("issues") for a,b in zip(reviews, observed_reviews)):
            errors.append("model_reviews_do_not_match_trace")
    if output["status"] == "completed":
        if run["mode"] == "real" and not any(c.get("actual_model") and c.get("request_id") for c in calls):
            errors.append("missing_real_call_metadata")
        draft = output["draft"]
        fingerprint = hash_json({"draft": draft, "request": request,
            "materials": run["materials_hash"], "rules": run["rules_hash"]})
        for name in ("estimate_duration", "check_rules"):
            check = output.get("checks", {}).get(name, {})
            if not check.get("passed") or check.get("fingerprint") != fingerprint:
                errors.append("invalid_check:" + name)
            if check.get("revision") != output["revision"]:
                errors.append("stale_revision:" + name)
            matches = [r for r in trace if r.get("decision", {}).get("action") == name
                and r.get("observation", {}).get("data") == check]
            if not matches:
                errors.append("check_without_tool_record:" + name)
        estimates = []
        for scene in draft["scenes"]:
            tracks = []
            for key, zh, en in [("narration", 4, 2.5), ("subtitle", 5, 3)]:
                value = scene[key]
                tracks.append(len(re.findall(r"[\u4e00-\u9fff]", value)) / zh
                    + len(re.findall(r"[A-Za-z0-9]+", value)) / en
                    + len(re.findall(r"[，。！？；,.!?;]", value)) * .15)
            estimates.append(round(max(*tracks, scene["min_seconds"]), 2))
        total = round(sum(estimates) + (len(estimates) - 1) * .25, 2)
        if total != output["estimated_total_seconds"] or total > request["target_seconds"]:
            errors.append("duration_recalculation_failed")
        evidence = {m["id"]: m for m in output["sources"]}
        originals = {m["id"]: m for m in materials}
        if any(originals.get(k) != v for k, v in evidence.items()):
            errors.append("modified_source")
        for scene in draft["scenes"]:
            for ident in scene["source_ids"]:
                if ident not in evidence:
                    errors.append("unretrieved_citation")
                elif request.get("product") and evidence[ident]["product"] != request["product"]:
                    errors.append("wrong_product_citation")
        revisions = read(folder / "revisions.json")
        if not revisions or revisions[-1]["draft"] != draft or revisions[-1]["hash"] != hash_json(draft):
            errors.append("final_draft_not_last_revision")
    return sorted(set(errors))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    cases = [args.folder] if (args.folder / "run.json").exists() else sorted(
        p for p in args.folder.iterdir() if p.is_dir())
    results = [{"case": p.name, "errors": verify(p)} for p in cases]
    report = {"runs": len(results), "passes": sum(not r["errors"] for r in results),
              "scope": "记录一致性、引用有效性、时长复算；不证明事实语义正确", "results": results}
    (args.folder / "artifact-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if cases and all(not r["errors"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
