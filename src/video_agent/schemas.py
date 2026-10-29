"""Small, strict JSON contracts, deliberately using only the standard library."""
import hashlib
import json
import math


class ContractError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def text(value, label, maximum=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ContractError(f"{label}: expected nonempty string, maximum {maximum} characters")
    return value.strip()


def number(value, label, low=0, high=600):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{label}: expected number")
    if not math.isfinite(value) or not low <= value <= high:
        raise ContractError(f"{label}: expected finite number in [{low}, {high}]")
    return float(value)


def validate_request(value):
    if not isinstance(value, dict):
        raise ContractError("request must be an object")
    required = ["theme", "audience", "platform", "target_seconds", "style"]
    missing = [k for k in required if value.get(k) is None or value.get(k) == ""]
    for k in required:
        if k not in missing:
            if k == "target_seconds":
                number(value[k], k, 1, 600)
            else:
                text(value[k], k, 500)
    for k in ["product", "instructions"]:
        if k in value:
            text(value[k], k)
    return missing


def validate_draft(value):
    if not isinstance(value, dict) or set(value) != {"title", "scenes"}:
        raise ContractError("draft requires exactly title and scenes")
    text(value["title"], "title", 120)
    scenes = value["scenes"]
    if not isinstance(scenes, list) or not 1 <= len(scenes) <= 12:
        raise ContractError("scenes must contain 1 to 12 items")
    for i, s in enumerate(scenes):
        keys = {"visual", "narration", "subtitle", "source_ids", "min_seconds"}
        if not isinstance(s, dict) or set(s) != keys:
            raise ContractError(f"scene {i}: expected {sorted(keys)}")
        text(s["visual"], "visual", 600)
        for k in ["narration", "subtitle"]:
            if not isinstance(s[k], str) or len(s[k]) > 1500:
                raise ContractError(f"scene {i}: invalid {k}")
        if not (s["narration"].strip() or s["subtitle"].strip()):
            raise ContractError(f"scene {i}: narration or subtitle is required")
        number(s["min_seconds"], "min_seconds", 1, 120)
        if not isinstance(s["source_ids"], list) or not s["source_ids"]:
            raise ContractError(f"scene {i}: at least one source ID required")
        for ident in s["source_ids"]:
            text(ident, "source ID", 80)
    return value


def ok(data):
    return {"ok": True, "data": data, "error": None}


def error(code, message, retryable=False):
    return {"ok": False, "data": None,
            "error": {"code": code, "message": message, "retryable": retryable}}
