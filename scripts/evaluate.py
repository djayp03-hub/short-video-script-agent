"""Frozen scenario runner: expected behavior is separate from the decision model."""
import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from video_agent.cli import execute_run, read, write
from video_agent.model_client import load_env


def scenarios():
    normal = read(ROOT / "data/request.json")
    missing = dict(normal)
    missing.pop("target_seconds")
    unknown = dict(normal, product="不存在的产品", theme="不存在的产品介绍")
    long_draft = {"title": "字幕入门", "scenes": [
        {"visual": "展示手动字幕编辑", "narration": "剪映盒演示版支持手动添加字幕。用户可以修改字幕文字和颜色。" * 3,
         "subtitle": "", "source_ids": ["P01"], "min_seconds": 2}]}
    forbidden = copy.deepcopy(long_draft)
    forbidden["scenes"][0]["narration"] = "剪映盒演示版支持自动语音转字幕，保证爆款，效率提升80%。"
    heldout = dict(normal, product="拾音笔校园版", theme="课堂录音与文件导出", target_seconds=25)
    cases = [
        {"id": "C01-normal", "request": normal, "expected": ["completed"]},
        {"id": "C02-missing", "request": missing, "expected": ["needs_input"]},
        {"id": "C03-no-material", "request": unknown, "expected": ["needs_input", "incomplete"]},
        {"id": "C04-tool-failure", "request": normal, "faults": {"search_materials": "always"}, "expected": ["incomplete", "needs_input"]},
        {"id": "C05-overlong", "request": dict(normal, target_seconds=15), "initial_draft": long_draft, "expected": ["completed"], "repair": True},
        {"id": "C06-rule-risk", "request": normal, "initial_draft": forbidden, "expected": ["completed", "incomplete"], "risk": True},
        {"id": "C07-recover-failure", "request": normal, "faults": {"search_materials": "once"}, "expected": ["completed"]},
        {"id": "C08-empty-rewrite", "request": normal, "faults": {"search_materials": "empty_once"}, "expected": ["completed"]},
        {"id": "H01-new-product", "request": heldout, "heldout": True, "expected": ["completed"]},
        {"id": "H02-paraphrase", "request": dict(heldout, theme="上课怎么留住老师讲的内容并带回电脑", style="简洁实用"), "heldout": True, "expected": ["completed"]},
        {"id": "H03-impossible", "request": dict(heldout, target_seconds=1, instructions="必须逐字包含：单次录音最长两小时；通过数据线导出；不提供云同步。不能省略。"), "heldout": True, "expected": ["incomplete", "needs_input"]},
    ]
    return cases


def audit_case(case, output):
    result = read(output / "output.json")
    trace = [json.loads(l) for l in (output / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    errors = []
    if result["status"] not in case["expected"]:
        errors.append("unexpected_terminal_status")
    if result["status"] == "completed":
        checks = result.get("checks", {})
        for k in ["estimate_duration", "check_rules"]:
            if not checks.get(k, {}).get("passed") or checks[k].get("revision") != result["revision"]:
                errors.append("invalid_completion_gate")
        if result.get("estimated_total_seconds", 1e9) > case["request"]["target_seconds"]:
            errors.append("over_duration")
    if case.get("repair"):
        failed = [r for r in trace if r.get("decision", {}).get("action") == "estimate_duration"
                  and r.get("observation", {}).get("data", {}) and r["observation"]["data"].get("passed") is False]
        if not failed or result.get("revision", 0) < 2:
            errors.append("missing_observed_repair")
    if case.get("risk") and result["status"] == "completed" and result.get("revision", 0) < 2:
        errors.append("unsafe_draft_not_revised")
    return {"case": case["id"], "status": result["status"], "automated_pass": not errors,
            "errors": errors, "steps": result["steps"], "human_review": "pending",
            "evidence": str(output.name), "initial_fixture": "initial_draft" in case,
            "heldout": case.get("heldout", False)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["mock", "real"], default="mock")
    p.add_argument("--output", required=True)
    p.add_argument("--env-file")
    p.add_argument("--cases", nargs="*")
    args = p.parse_args()
    if args.env_file:
        load_env(args.env_file)
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=False)
    cases = [c for c in scenarios() if not args.cases or c["id"] in args.cases]
    if not cases:
        p.error("no matching cases")
    write(destination / "case-manifest.json", cases)
    rows = []
    for case in cases:
        materials = read(ROOT / "data" / ("heldout_materials.json" if case.get("heldout") else "materials.json"))
        output = destination / case["id"]
        execute_run(case["request"], materials, read(ROOT / "data/brand_rules.json"), output,
                    args.mode, case.get("faults"), case.get("initial_draft"))
        row = audit_case(case, output)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        write(destination / "summary.json", {"mode": args.mode, "total": len(rows),
            "automated_passes": sum(r["automated_pass"] for r in rows), "cases": rows,
            "scope": "自动合同验收，不是独立人工内容评分或泛化能力证明"})
    return 0 if all(r["automated_pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
