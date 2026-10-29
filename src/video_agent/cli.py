import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .agent import Agent
from .mock_model import MockModel
from .model_client import LiveModel, ModelError, load_env
from .schemas import ContractError, digest
from .tools import ToolBox

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def code_hash():
    root = Path(__file__).parent
    return digest({p.name: p.read_text(encoding="utf-8") for p in sorted(root.glob("*.py"))})


def execute_run(request, materials, rules, output_dir, mode="mock", faults=None,
                initial_draft=None, max_steps=12, max_seconds=240):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    source_hash = code_hash()
    start = time.monotonic()
    write(output / "input.json", request)
    write(output / "materials.json", materials)
    write(output / "rules.json", rules)
    if initial_draft:
        write(output / "initial-draft.json", initial_draft)
    model = None
    agent = None
    try:
        model = LiveModel() if mode == "real" else MockModel()
        tools = ToolBox(materials, rules, faults)
        agent = Agent(model, tools, max_steps, max_seconds)
        result = agent.run(request, initial_draft)
    except (ContractError, ModelError, KeyError) as exc:
        result = {"status": "failed", "reason": str(exc), "mode": mode, "steps": 0}
    trace = agent.trace if agent else []
    write(output / "output.json", result)
    write(output / "revisions.json", agent.revisions if agent else [])
    (output / "trace.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in trace), encoding="utf-8")
    calls = model.calls if model else []
    write(output / "model-calls.json", calls)
    write(output / "run.json", {"started_at_utc": started,
        "elapsed_seconds": round(time.monotonic() - start, 3), "python": platform.python_version(),
        "mode": mode, "model": getattr(model, "model", None), "source_hash": source_hash,
        "materials_hash": digest(materials), "rules_hash": digest(rules), "input_hash": digest(request),
        "faults": faults or {}, "initial_draft_fixture": initial_draft is not None,
        "max_steps": max_steps, "max_seconds": max_seconds, "status": result["status"],
        "model_calls": len(calls), "usage": [c.get("usage") for c in calls],
        "endpoint": getattr(model, "base_url", None)})
    if result.get("draft"):
        draft = result["draft"]
        lines = ["# " + draft["title"], "", f"状态：{result['status']}；预计总时长：{result.get('estimated_total_seconds')} 秒", ""]
        timings = result.get("checks", {}).get("estimate_duration", {}).get("scenes", [])
        for i, scene in enumerate(draft["scenes"]):
            duration = timings[i]["seconds"] if i < len(timings) else "未检查"
            lines += [f"## 镜头 {i + 1}（{duration} 秒）", "", "画面：" + scene["visual"],
                      "", "旁白：" + scene["narration"], "", "字幕：" + scene["subtitle"],
                      "", "来源：" + ", ".join(scene["source_ids"]), ""]
        lines += ["自动审核不替代人工事实复核；时长为估算。"]
        (output / "script.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="短视频脚本 Agent：离线流程模拟 / 真实模型决策")
    parser.add_argument("--input", default=str(PROJECT_ROOT / "data/request.json"))
    parser.add_argument("--materials", default=str(PROJECT_ROOT / "data/materials.json"))
    parser.add_argument("--rules", default=str(PROJECT_ROOT / "data/brand_rules.json"))
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--env-file", help="显式指定凭据文件；不复制到运行材料")
    parser.add_argument("--output", help="新的运行目录；省略时自动在项目 runs 下创建，已有目录不会覆盖")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--max-seconds", type=float, default=240)
    parser.add_argument("--faults", help="故障注入 JSON 文件")
    parser.add_argument("--initial-draft", help="明确标记的初稿测试夹具")
    args = parser.parse_args()
    if args.output is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        args.output = str(PROJECT_ROOT / "runs" / f"{args.mode}-{stamp}-{uuid4().hex[:6]}")
    try:
        if args.env_file:
            load_env(args.env_file)
        result = execute_run(read(args.input), read(args.materials), read(args.rules), args.output,
            args.mode, read(args.faults) if args.faults else None,
            read(args.initial_draft) if args.initial_draft else None, args.max_steps, args.max_seconds)
        print(json.dumps({"status": result["status"], "reason": result["reason"],
                          "output": str(Path(args.output).resolve())}, ensure_ascii=False))
        return 0 if result["status"] == "completed" else 2
    except (OSError, ValueError) as exc:
        print(f"CLI error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
