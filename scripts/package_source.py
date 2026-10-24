#!/usr/bin/env python3
"""Deterministic source-only RC ZIP with fail-closed content and extraction checks.

No GA tagging, release API, runtime/models/media, source mutation or auto-posting.
ZIP contains one top-level directory and the verified source manifest. This is
transport integrity, not authentication or independent Windows video acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import release_manifest as release

ROOT_NAME = "AI-News-Video-Skill-1.0.0-rc.2"
DEFAULT_FILENAME = ROOT_NAME + "-source.zip"
ENTRY_TIME = (2026, 1, 1, 0, 0, 0)
MAX_MEMBER_BYTES = 20 * 1024 * 1024
MAX_ZIP_UNPACKED_BYTES = 50 * 1024 * 1024

def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _metadata(data: bytes, members: dict[str, dict]) -> dict:
    return {"schema": "AI_NEWS_SOURCE_ZIP_RC_V1",
            "version": release.VERSION,
            "release_status": "RELEASE_CANDIDATE_NOT_GA",
            "source_files": len(members),
            "archive_top_level_directory": ROOT_NAME,
            "manifest_sha256": sha_bytes(data),
            "windows_independent_video_acceptance": False,
            "automatic_publication": False}

def _name(name: str) -> str:
    prefix = ROOT_NAME + "/"
    if not name.startswith(prefix) or name.endswith("/") or "\\" in name:
        raise ValueError("unsafe ZIP member root/name")
    leaf = name[len(prefix):]
    parts = PurePosixPath(leaf).parts
    if not parts or any(p in ("", ".", "..") for p in parts) or leaf.startswith("/"):
        raise ValueError("unsafe ZIP relative path")
    if len(leaf) > 235 or any(ord(c)<32 for c in leaf):
        raise ValueError("unsafe ZIP path characters/length")
    return leaf

def verify_zip(path: Path, expected_manifest_sha256: str | None = None) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError("source ZIP does not exist")
    if expected_manifest_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", expected_manifest_sha256):
        raise ValueError("expected manifest SHA-256 must be 64 hex characters")
    with zipfile.ZipFile(path, "r", allowZip64=False) as z:
        infos = z.infolist()
        if len(infos)<50 or len(infos)>1500:
            raise ValueError("source ZIP unexpected entry count")
        names = [_name(i.filename) for i in infos]
        if len(set(n.casefold() for n in names))!=len(names):
            raise ValueError("duplicate/case-colliding ZIP paths")
        for info in infos:
            mode=(info.external_attr>>16)&0o170000
            if (info.flag_bits&1 or mode==0o120000 or info.file_size>MAX_MEMBER_BYTES
                    or info.compress_type!=zipfile.ZIP_DEFLATED):
                raise ValueError("encrypted, linked, oversized or unsupported ZIP member")
        if sum(i.file_size for i in infos)>MAX_ZIP_UNPACKED_BYTES:
            raise ValueError("source ZIP exceeds unpacked byte budget")
        if release.MANIFEST_NAME not in names:
            raise ValueError("ZIP missing release manifest")
        manifest_content=z.read(ROOT_NAME+"/"+release.MANIFEST_NAME)
        if expected_manifest_sha256 and sha_bytes(manifest_content)!=expected_manifest_sha256.lower():
            raise ValueError("manifest does not match independently supplied SHA-256")
        manifest=json.loads(manifest_content)
        if (manifest.get("schema")!=release.SCHEMA or manifest.get("version")!=release.VERSION
                or manifest.get("release_status")!="RELEASE_CANDIDATE_NOT_GA"
                or manifest.get("windows_independent_acceptance")!="NOT_RUN_USER_RESPONSIBILITY"
                or manifest.get("automatic_publication") is not False):
            raise ValueError("invalid source release candidate status/metadata")
        entries={v["path"]:v for v in manifest["files"]}
        expected=set(entries)|{release.MANIFEST_NAME}
        if set(names)!=expected or len(entries)!=manifest["total_files"]:
            raise ValueError("ZIP files do not match manifest inventory")
        if sum(v["bytes"] for v in entries.values())!=manifest["total_bytes"]:
            raise ValueError("manifest has incorrect source byte count")
        if release._file_set_hash(manifest["files"])!=manifest["content_set_sha256"]:
            raise ValueError("source manifest content-set hash mismatch")
        for info in infos:
            rel=_name(info.filename)
            payload=z.read(info.filename)
            if len(payload)!=info.file_size:
                raise ValueError("ZIP member length differs from entry")
            if rel!=release.MANIFEST_NAME:
                row=entries[rel]
                if len(payload)!=row["bytes"] or sha_bytes(payload)!=row["sha256"]:
                    raise ValueError("ZIP member SHA-256 mismatch: "+rel)
        with tempfile.TemporaryDirectory(prefix="verified-news-skill-") as tmp:
            root=Path(tmp)/ROOT_NAME
            root.mkdir()
            for info in infos:
                relative=_name(info.filename)
                dest=root.joinpath(*PurePosixPath(relative).parts)
                dest.parent.mkdir(parents=True,exist_ok=True)
                with dest.open("xb") as stream:
                    stream.write(z.read(info.filename))
            release.verify(root)
        return {**_metadata(manifest_content,entries),
                "status":"RC_ZIP_VERIFIED",
                "archive_sha256":release.sha256_file(path),
                "zip_entries":len(infos),
                "unpacked_source_bytes":manifest["total_bytes"],
                "windows_extraction_path_checks_passed":True}

def create(source: Path, destination: Path) -> dict:
    source=Path(source).resolve()
    destination=Path(destination).absolute()
    if destination.exists():
        raise FileExistsError("ZIP destination already exists; refuse overwrite")
    if destination==source or destination.is_relative_to(source):
        raise ValueError("ZIP destination must be outside Skill source")
    release.verify(source)
    raw_manifest=(source/release.MANIFEST_NAME).read_bytes()
    manifest=json.loads(raw_manifest)
    if (manifest.get("release_status")!="RELEASE_CANDIDATE_NOT_GA"
            or manifest.get("windows_independent_acceptance")!="NOT_RUN_USER_RESPONSIBILITY"):
        raise ValueError("no GA release without verified Windows evidence")
    destination.parent.mkdir(parents=True,exist_ok=True)
    ordered=sorted((row["path"] for row in manifest["files"])+[release.MANIFEST_NAME],key=str.casefold)
    created=False
    try:
        with destination.open("xb") as output:
            created=True
            with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
                for rel in ordered:
                    data=(source/rel).read_bytes()
                    if rel!=release.MANIFEST_NAME:
                        expected=next(x for x in manifest["files"] if x["path"]==rel)
                        if len(data)!=expected["bytes"] or sha_bytes(data)!=expected["sha256"]:
                            raise ValueError("source changed while creating ZIP: "+rel)
                    info=zipfile.ZipInfo(ROOT_NAME+"/"+rel,date_time=ENTRY_TIME)
                    info.compress_type=zipfile.ZIP_DEFLATED
                    info.create_system=3
                    info.external_attr=(0o100644<<16)
                    info.flag_bits|=0x800
                    archive.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
        verified=verify_zip(destination,sha_bytes(raw_manifest))
        return {"status":"RC_SOURCE_ZIP_CREATED_VERIFIED",
                "zip_file":str(destination),"zip_sha256":release.sha256_file(destination),
                **verified}
    except BaseException:
        if created:
            destination.unlink(missing_ok=True)
        raise

def main()->None:
    ap=argparse.ArgumentParser(description="Package or independently verify portable source-only RC ZIP")
    ap.add_argument("command",choices=("build","verify"))
    ap.add_argument("--source",type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument("--zip",type=Path,required=True)
    ap.add_argument("--expect-manifest-sha256")
    args=ap.parse_args()
    try:
        result=(create(args.source,args.zip) if args.command=="build" else
                verify_zip(args.zip,args.expect_manifest_sha256))
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,TypeError,json.JSONDecodeError,zipfile.BadZipFile) as exc:
        ap.exit(2,"RC_PACKAGE_ERROR: "+str(exc)+"\n")

if __name__=="__main__":
    main()
