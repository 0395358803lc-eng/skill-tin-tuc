#!/usr/bin/env python3
"""Read-only AI Agent companion for intake, job discovery and safe next-step advice.

Never creates jobs, user selection, script approval, source evidence, video or uploads.
All state transitions MUST use the existing workflow.py human-gated CLI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import news_rss
import job_integrity as integrity
import render_video as legacy

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ.get("NEWS_SKILL_RUNTIME", ROOT.parent / (ROOT.name + "-runtime")))
DEFAULT_JOBS = RUNTIME / "jobs"

SCHEMA = "AGENT_BRIDGE_V1"
DEFAULTS = {
    "category": "general", "hours": 24, "language": "vi-VN",
    "target_seconds": 60, "aspect_ratio": "both", "tone": "neutral",
}
SUPPORTED = {
    "country": set(news_rss.COUNTRIES),
    "category": set(news_rss.CATEGORIES),
    "hours": {6, 24, 72, 168},
    "language": {"vi-VN", "en-US", "en-GB"},
    "target_seconds": {30, 60, 90, 180},
    "aspect_ratio": {"9:16", "16:9", "both"},
    "tone": {"neutral", "fast", "in_depth"},
}
COUNTRY_WORDS = {
    "VN": ("viet nam", "vietnam"),
    "US": ("hoa ky", "nuoc my", "united states", "usa", "u s a"),
    "GB": ("anh quoc", "vuong quoc anh", "united kingdom", "britain", "uk"),
    "JP": ("nhat ban", "japan"),
    "KR": ("han quoc", "south korea"),
    "CN": ("trung quoc", "china"),
    "FR": ("nuoc phap", "france"),
    "DE": ("duc", "germany"),
    "TH": ("thai lan", "thailand"),
    "WORLD": ("the gioi", "toan cau", "quoc te", "world news", "global news"),
}
CATEGORY_WORDS = {
    "technology": ("cong nghe", "technology", "tech news", "tri tue nhan tao", "artificial intelligence"),
    "economy": ("kinh te", "tai chinh", "business", "finance", "economy"),
    "politics": ("chinh tri", "politics"),
    "science": ("khoa hoc", "science"),
    "entertainment": ("giai tri", "entertainment"),
    "sports": ("the thao", "sports"),
    "environment": ("moi truong", "khi hau", "environment", "climate"),
    "health": ("suc khoe", "y te", "health", "medical"),
    "general": ("tong hop", "thoi su", "general news", "breaking news"),
}
HUMAN_ACTIONS = {
    "CREATED": ("P1_DISCOVER", "workflow.py discover", False,
                "Có thể chạy discover, nhưng ứng viên RSS chưa được kiểm chứng."),
    "AWAITING_EVIDENCE": ("P2_READ_ORIGINAL_SOURCES", None, True,
                          "AI Agent cần đọc nguồn gốc độc lập, lập EVIDENCE.json thật rồi mới chạy workflow.py evidence."),
    "NEEDS_EVIDENCE": ("P2_RESEARCH_OR_START_NEW_JOB", None, True,
                       "Chưa đủ chứng cứ; không tự chuyển tiếp hoặc bịa tin. Cân nhắc job nghiên cứu mới."),
    "AWAITING_SELECTION": ("P3_WAIT_USER_SELECTION", None, True,
                           "Trình nguồn và ID sự kiện; đợi thông điệp chọn tin thật từ người dùng."),
    "AWAITING_SCRIPT": ("P4_COMPOSE_DRAFT", None, True,
                        "Soạn SCRIPT.json từ nguồn đã được người dùng chọn, đo thời lượng trước khi đóng băng draft."),
    "AWAITING_APPROVAL": ("P5_WAIT_EXACT_SCRIPT_APPROVAL", None, True,
                          "Trình đầy đủ draft và SHA-256; đợi phê duyệt riêng từ người dùng."),
    "APPROVED": ("P6_RENDER_APPROVED_ONLY", "workflow.py render", False,
                 "Trước khi render cần doctor/rights PASS; approved.json bất biến."),
    "RENDERED": ("P7_TECHNICAL_QA", "workflow.py qa", False,
                 "Chạy QA trên đầu ra đã render; không tự sửa approved.json."),
    "TECHNICAL_QA_FAILED": ("P7_MANUAL_QA_REVIEW", None, True,
                            "Dừng và kiểm tra lỗi QA; chỉ phục hồi loại lỗi được workflow cho phép."),
    "TECHNICAL_QA_PASSED": ("P7_HANDOFF", "workflow.py handoff", False,
                            "Có thể bàn giao, vẫn phải đợi người dùng duyệt video cuối và tự đăng."),
    "AWAITING_HUMAN_FINAL_REVIEW": ("HUMAN_REVIEW_AND_MANUAL_UPLOAD", None, True,
                                   "Người dùng xem/nghe, kiểm chứng thời sự/bản quyền rồi tự đăng, không auto-upload."),
}


def plain(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return value.replace("đ", "d").replace("Đ", "d")


def contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text))


def lexical_matches(text: str, phrases: dict[str, tuple[str, ...]]) -> list[str]:
    return [code for code, values in phrases.items() if any(contains_phrase(text, token) for token in values)]


def unique_or_issue(field: str, values: list, issues: list[str]):
    dedup = list(dict.fromkeys(values))
    if len(dedup) > 1:
        issues.append("AMBIGUOUS_" + field.upper() + ": " + ", ".join(map(str, dedup)))
        return None
    return dedup[0] if dedup else None


def intake(text: str) -> dict:
    """Extract explicit hints conservatively. The LLM remains responsible for meaning."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty user request")
    if len(text) > 12000:
        raise ValueError("request too long; ask for a shorter request")
    normalized = plain(text)
    issues: list[str] = []
    supplied: dict[str, object] = {}
    defaults_used: list[str] = []

    raw_countries = lexical_matches(normalized, COUNTRY_WORDS)
    # Recognize explicit country codes, not English pronouns like lowercase 'us'.
    for country_code in ("US", "VN", "GB", "JP", "KR", "WORLD"):
        if re.search(r"(?<![A-Za-z])" + country_code + r"(?![A-Za-z])", text):
            raw_countries.append(country_code)
    # Ambiguous bare 'Mỹ/my' is accepted ONLY when the actual accented Vietnamese word is present.
    if contains_phrase(text.casefold(), "mỹ"):
        raw_countries.append("US")
    supplied["country"] = unique_or_issue("country", raw_countries, issues)
    if supplied["country"] is None and not raw_countries:
        issues.append("MISSING_COUNTRY: specify the location/edition of news, or WORLD")

    raw_categories = lexical_matches(normalized, CATEGORY_WORDS)
    # "general" is a broad framing, not a conflict when paired with a specific topic.
    specific = [x for x in raw_categories if x != "general"]
    raw_categories = specific if specific else raw_categories
    supplied["category"] = unique_or_issue("category", raw_categories, issues)

    # Explicit clock durations only; do not treat '3 news items' as video duration.
    duration_tokens = []
    for m in re.finditer(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(giay|seconds?|secs?|s|phut|minutes?|mins?)(?!\w)", normalized):
        number = float(m.group(1).replace(",", "."))
        sec = round(number * (60 if m.group(2) in ("phut", "minute", "minutes", "min", "mins") else 1))
        duration_tokens.append(sec)
    # '60s' / '90 giây': regex above. Require strict valid seconds.
    supplied["target_seconds"] = unique_or_issue("target_seconds", duration_tokens, issues)

    ranges = []
    for m in re.finditer(r"(?<!\d)(\d+)\s*(gio|hours?|h|ngay|days?|d)(?:\s*(?:qua|gan day|past))?(?!\w)", normalized):
        value = int(m.group(1)) * (24 if m.group(2) in ("ngay", "day", "days", "d") else 1)
        ranges.append(value)
    supplied["hours"] = unique_or_issue("hours", ranges, issues)

    explicit_aspects = []
    if re.search(r"(?<!\d)9\s*[:/]\s*16(?!\d)", normalized):
        explicit_aspects.append("9:16")
    if re.search(r"(?<!\d)16\s*[:/]\s*9(?!\d)", normalized):
        explicit_aspects.append("16:9")
    if any(contains_phrase(normalized, x) for x in ("ca hai ti le", "hai dinh dang", "both aspects", "both formats", "both ratios")):
        explicit_aspects = ["both"]
    elif set(explicit_aspects) == {"9:16", "16:9"}:
        explicit_aspects = ["both"]
    elif not explicit_aspects and any(contains_phrase(normalized, x) for x in ("tiktok", "youtube shorts", "shorts")):
        explicit_aspects = ["9:16"]
    supplied["aspect_ratio"] = unique_or_issue("aspect_ratio", explicit_aspects, issues)

    explicit_langs = []
    if any(contains_phrase(normalized, x) for x in ("tieng viet", "vietnamese language", "viet voice")):
        explicit_langs.append("vi-VN")
    if any(contains_phrase(normalized, x) for x in ("tieng anh", "english language", "english voice")):
        explicit_langs.append("en-US")
    supplied["language"] = unique_or_issue("language", explicit_langs, issues)

    tones = []
    if any(contains_phrase(normalized, x) for x in ("nhanh", "fast pace", "fast paced")):
        tones.append("fast")
    if any(contains_phrase(normalized, x) for x in ("chuyen sau", "in depth", "deep dive")):
        tones.append("in_depth")
    supplied["tone"] = unique_or_issue("tone", tones, issues)

    for key, default in DEFAULTS.items():
        if supplied[key] is None:
            if any(item.startswith("AMBIGUOUS_" + key.upper()) for item in issues):
                continue
            supplied[key] = default
            defaults_used.append(key)
        if supplied[key] not in SUPPORTED[key]:
            issues.append("UNSUPPORTED_" + key.upper() + ": " + str(supplied[key]))

    ready = not issues and all(supplied.get(x) in SUPPORTED[x] for x in SUPPORTED)
    args = None
    if ready:
        args = ["--country", str(supplied["country"]), "--category", str(supplied["category"]),
                "--hours", str(supplied["hours"]), "--language", str(supplied["language"]),
                "--seconds", str(supplied["target_seconds"]), "--aspect", str(supplied["aspect_ratio"]),
                "--tone", str(supplied["tone"])]
    return {
        "schema": SCHEMA, "operation": "INTAKE_ADVISORY_ONLY", "ready_for_review": ready,
        "parameters": supplied, "defaults_applied": defaults_used,
        "ambiguities_and_missing": issues,
        "workflow_init_arguments": args,
        "requires_agent_semantic_review": True,
        "creates_job": False, "user_selection_received": False,
        "user_script_approval_received": False,
        "advice": "Agent semantic review: check event location vs RSS edition, dates, nuances and all defaults with user before invoking workflow.py init.",
    }


def scoped_job(job: Path, jobs_root: Path) -> Path:
    root = integrity.validate_jobs_root(jobs_root, ROOT)
    path = job.resolve()
    if path.parent != root or job.is_symlink() or not path.is_dir():
        raise ValueError("job must be an existing direct child of the explicitly selected jobs root")
    if not (path / "job.json").is_file() or (path / "job.json").is_symlink():
        raise ValueError("job metadata missing or is a symbolic link")
    meta = json.loads((path / "job.json").read_text(encoding="utf-8-sig"))
    if not isinstance(meta, dict) or meta.get("schema_version") != 1 or meta.get("job_id") != path.name:
        raise ValueError("malformed job metadata")
    if not isinstance(meta.get("parameters"), dict):
        raise ValueError("missing job parameters")
    return path


def job_state(job: Path) -> dict:
    """Read-only stage and checkpoint assessment without renderer dependencies."""
    meta = json.loads((job / "job.json").read_text(encoding="utf-8-sig"))
    if (job / "approved.json").is_file():
        approved = json.loads((job / "approved.json").read_text(encoding="utf-8-sig"))
        legacy.validate_brief(approved, False)
    if (job / "handoff.json").is_file():
        stage = "AWAITING_HUMAN_FINAL_REVIEW"
    else:
        qa = next((job / name for name in (
            "technical_qa_recheck_02.json", "technical_qa_recheck.json", "technical_qa.json")
            if (job / name).is_file()), None)
        if qa is not None:
            report = json.loads(qa.read_text(encoding="utf-8-sig"))
            stage = "TECHNICAL_QA_PASSED" if report.get("technical_pass") is True else "TECHNICAL_QA_FAILED"
        elif (job / "render_result.json").is_file():
            stage = "RENDERED"
        elif (job / "approved.json").is_file():
            stage = "APPROVED"
        elif (job / "draft.json").is_file():
            stage = "AWAITING_APPROVAL"
        elif (job / "selection.json").is_file():
            stage = "AWAITING_SCRIPT"
        elif (job / "review.json").is_file():
            review = json.loads((job / "review.json").read_text(encoding="utf-8-sig"))
            stage = "AWAITING_SELECTION" if review.get("eligible_count", 0) > 0 else "NEEDS_EVIDENCE"
        elif (job / "queue.json").is_file():
            stage = "AWAITING_EVIDENCE"
        else:
            stage = "CREATED"
    return {"stage": stage, "job_id": meta["job_id"],
            "parameters": meta["parameters"], "recovery": integrity.recovery_plan(job)}


def inspect(job: Path, jobs_root: Path) -> dict:
    current = scoped_job(job, jobs_root)
    result = job_state(current)
    recovery = result["recovery"]
    step = HUMAN_ACTIONS.get(result["stage"])
    if step is None:
        return {"schema": SCHEMA, "job_directory": str(current), "blocked": True,
                "reason": "UNKNOWN_STAGE_REQUIRES_MANUAL_REVIEW", "state": result}
    phase, suggested, human_needed, guidance = step
    safe = recovery["safe_to_mutate"]
    blocked = not safe or suggested is None
    if not safe:
        guidance = "RECOVERY_BLOCK: read checkpoint and lock details; do not mutate or start an additional render attempt."
        suggested = None
        human_needed = True
    return {
        "schema": SCHEMA, "operation": "READ_ONLY_JOB_INSPECTION",
        "job_directory": str(current), "job_id": result["job_id"],
        "stage": result["stage"], "phase": phase, "blocked": blocked,
        "safe_to_mutate": safe, "requires_human_action": human_needed,
        "suggested_workflow_command": suggested,
        "guidance": guidance,
        "recovery": recovery, "job_parameters": result["parameters"],
        "human_gates_preserved": True, "automatic_publication": False,
    }


def catalog(jobs_root: Path, limit: int = 100) -> dict:
    root = integrity.validate_jobs_root(jobs_root, ROOT)
    if not root.is_dir():
        return {"schema": SCHEMA, "jobs_root": str(root), "jobs": [], "total": 0}
    entries = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if child.is_symlink() or not child.is_dir() or not (child / "job.json").is_file():
            continue
        # Fail closed on invalid jobs rather than claiming they're safe.
        try:
            job = scoped_job(child, root)
            state = inspect(job, root)
            entries.append({"job_id": job.name, "job_directory": str(job),
                            "stage": state["stage"], "blocked": state["blocked"],
                            "safe_to_mutate": state["safe_to_mutate"]})
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
            entries.append({"job_id": child.name, "job_directory": str(child),
                            "blocked": True, "stage": "INVALID_OR_UNREADABLE"})
        if len(entries) > limit:
            break
    truncated = len(entries) > limit
    return {"schema": SCHEMA, "operation": "READ_ONLY_CATALOG",
            "jobs_root": str(root), "jobs": entries[:limit], "listed": min(len(entries), limit),
            "total": None if truncated else len(entries),
            "truncated": truncated, "select_exact_job_before_mutation": True}


def main() -> None:
    ap = argparse.ArgumentParser(description="Read-only support for AI News Video agents")
    sub = ap.add_subparsers(dest="command", required=True)
    req = sub.add_parser("intake")
    group = req.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="Natural-language request; never persisted")
    group.add_argument("--text-file", type=Path, help="Existing UTF-8 request file; only read")
    view = sub.add_parser("inspect")
    view.add_argument("--job", required=True, type=Path)
    view.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS)
    listing = sub.add_parser("list")
    listing.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS)
    listing.add_argument("--limit", type=int, default=100)
    opts = ap.parse_args()
    try:
        if opts.command == "intake":
            text = opts.text if opts.text is not None else opts.text_file.read_text(encoding="utf-8-sig")
            result = intake(text)
        elif opts.command == "inspect":
            result = inspect(opts.job, opts.jobs_root)
        else:
            if not 1 <= opts.limit <= 100:
                raise ValueError("list limit must be 1–100")
            result = catalog(opts.jobs_root, opts.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        ap.exit(2, "AGENT_BRIDGE_ERROR: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
