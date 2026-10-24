#!/usr/bin/env python3
"""Deterministic, source-only release manifest for manually transferred ZIPs.

Build is explicit and create-only. Verify is read-only. Neither command downloads,
installs, renders, modifies runtime, or publishes video. The manifest excludes
itself to avoid a self-referential digest; verify against a trusted external hash
of the manifest if authenticity (not just internal consistency) matters.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import release_audit

MANIFEST_NAME = "RELEASE_MANIFEST_SHA256.json"
SCHEMA = "AI_NEWS_SKILL_SOURCE_RELEASE_V1"
VERSION = "1.0.0-rc.2"
VALID_SUFFIXES = {".py", ".md", ".ps1", ".txt", ".jsx", ".json"}
FORBIDDEN_COMPONENTS = {
    ".git", ".venv", "__pycache__", "node_modules", "_work",
    "output", "logs", "jobs", "deliveries", ".idea", ".vscode",
    "dist", "build", "coverage", ".pytest_cache",
}
FORBIDDEN_EXTENSIONS = {
    ".zip", ".7z", ".rar", ".exe", ".dll", ".pyd", ".pyc",
    ".mp4", ".mov", ".mkv", ".mp3", ".wav", ".onnx",
    ".db", ".sqlite", ".sqlite3", ".bak", ".tmp", ".log",
    ".pending", ".pem", ".key", ".p12", ".pfx",
}
FORBIDDEN_NAMES = {
    "thumbs.db", "desktop.ini", ".ds_store", ".env",
    ".env.local", "id_rsa", "id_ed25519",
}
WINDOWS_RESERVED = re.compile(r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _unsafe_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def scan(root: Path) -> list[dict]:
    """Inventory every item and fail closed on links, forbidden artifacts, and collisions."""
    root = Path(root).absolute()
    if not root.is_dir() or _unsafe_link(root):
        raise ValueError("Skill source must be an existing regular directory")
    items = []
    casefolded: set[str] = set()
    for folder, directories, filenames in os.walk(root, topdown=True, followlinks=False):
        base = Path(folder)
        for dirname in directories:
            child = base / dirname
            if _unsafe_link(child):
                raise ValueError("Directory link/reparse point forbidden: " + str(child.relative_to(root)))
            if dirname.casefold() in FORBIDDEN_COMPONENTS:
                raise ValueError("Runtime/cache folder in source: " + str(child.relative_to(root)))
            if WINDOWS_RESERVED.fullmatch(dirname) or dirname.endswith((" ", ".")):
                raise ValueError("Windows-unsafe folder name: " + str(child.relative_to(root)))
        for name in filenames:
            path = base / name
            rel = path.relative_to(root).as_posix()
            if _unsafe_link(path):
                raise ValueError("Symlink in release source: " + rel)
            if name.casefold() == MANIFEST_NAME.casefold():
                if rel != MANIFEST_NAME:
                    raise ValueError("Manifest must be at source root with exact name")
                continue
            if name.casefold() in FORBIDDEN_NAMES or name.casefold().startswith(".env."):
                raise ValueError("Secret/environment file in source: " + rel)
            if WINDOWS_RESERVED.fullmatch(name) or name.endswith((" ", ".")):
                raise ValueError("Windows-unsafe file name: " + rel)
            if name.casefold().startswith((".", "~")) and name != ".gitignore":
                raise ValueError("Hidden/temporary file in source: " + rel)
            if path.suffix.casefold() in FORBIDDEN_EXTENSIONS:
                raise ValueError("Non-source binary/temporary artifact: " + rel)
            if name != ".gitignore" and path.suffix.casefold() not in VALID_SUFFIXES:
                raise ValueError("Unexpected source file type: " + rel)
            casefold = rel.casefold()
            if casefold in casefolded:
                raise ValueError("Windows case-insensitive path collision: " + rel)
            casefolded.add(casefold)
            items.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    items.sort(key=lambda item: item["path"].casefold())
    return items


def _file_set_hash(items: list[dict]) -> str:
    canonical = json.dumps(items, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def create_manifest(root: Path) -> dict:
    root = Path(root).resolve()
    if not (root / "SKILL.md").is_file():
        raise ValueError("SKILL.md missing; incorrect release root")
    skill = (root / "SKILL.md").read_text(encoding="utf-8-sig")
    if "version: " + VERSION not in skill:
        raise ValueError("SKILL.md version differs from release candidate")
    package = json.loads((root / "remotion-template/package.json").read_text(encoding="utf-8-sig"))
    lock = json.loads((root / "remotion-template/package-lock.json").read_text(encoding="utf-8-sig"))
    if any(value != VERSION for value in (
        package.get("version"), lock.get("version"), lock.get("packages", {}).get("", {}).get("version")
    )):
        raise ValueError("Remotion package and lock versions do not match")
    audit = release_audit.audit(root)
    if audit["status"] != "SOURCE_AUDIT_PASS":
        raise ValueError("Source audit failed: " + json.dumps(audit["issues"], ensure_ascii=False))
    items = scan(root)
    return {
        "schema": SCHEMA, "name": "ai-news-video", "version": VERSION,
        "release_status": "RELEASE_CANDIDATE_NOT_GA",
        "windows_independent_acceptance": "NOT_RUN_USER_RESPONSIBILITY",
        "source_only": True, "automatic_publication": False,
        "manifest_self_hash_excluded": True, "hash_algorithm": "SHA-256",
        "total_files": len(items), "total_bytes": sum(x["bytes"] for x in items),
        "content_set_sha256": _file_set_hash(items),
        "files": items,
    }


def save(root: Path) -> dict:
    root = Path(root).resolve()
    path = root / MANIFEST_NAME
    if path.exists():
        raise FileExistsError("Manifest already exists: refuse overwrite; verify first")
    value = create_manifest(root)
    data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # Exclusive creation; do not overwrite a prior manifest or another process's output.
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"status": "MANIFEST_CREATED", "version": VERSION, "source_files": value["total_files"],
            "manifest_file": MANIFEST_NAME, "manifest_sha256": sha256_file(path),
            "content_set_sha256": value["content_set_sha256"]}


def verify(root: Path) -> dict:
    root = Path(root).resolve()
    path = root / MANIFEST_NAME
    if not path.is_file() or _unsafe_link(path):
        raise ValueError("Release manifest missing or is a link")
    loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    generated = create_manifest(root)
    # Compare all fields; unexpected fields and altered files are not allowed.
    if loaded != generated:
        old = {x["path"]: x for x in loaded.get("files", []) if isinstance(x, dict) and "path" in x}
        new = {x["path"]: x for x in generated["files"]}
        missing = sorted(old.keys() - new.keys())
        extra = sorted(new.keys() - old.keys())
        altered = sorted(key for key in old.keys() & new.keys() if old[key] != new[key])
        raise ValueError("Release content mismatch; missing=" + repr(missing) +
                         "; extra=" + repr(extra) + "; altered=" + repr(altered) +
                         "; or manifest metadata differs")
    return {
        "status": "RELEASE_MANIFEST_PASS", "version": VERSION,
        "release_status": generated["release_status"],
        "source_files": generated["total_files"],
        "total_bytes": generated["total_bytes"],
        "content_set_sha256": generated["content_set_sha256"],
        "manifest_sha256": sha256_file(path),
        "windows_independent_acceptance": "NOT_RUN_USER_RESPONSIBILITY",
        "zip_created": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Source-only RC freeze: build once or verify read-only")
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = save(args.source) if args.command == "build" else verify(args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(2, "RELEASE_MANIFEST_ERROR: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
