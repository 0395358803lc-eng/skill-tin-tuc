#!/usr/bin/env python3
"""Discover user-installed LOCAL Piper voices; never fetches models or uses cloud TTS."""
from __future__ import annotations
import json
import re
from pathlib import Path

VOICE_NAME=re.compile(r"^[a-z]{2,3}_[A-Z]{2}(?:[-_][\w-]+)?$")
QUALITY={"high":3,"medium":2,"low":1}

def available(models_dir:Path, language:str)->list[dict]:
    if language not in ("vi-VN","en-US","en-GB"):
        raise ValueError("unsupported voice language")
    prefix="vi_" if language.startswith("vi") else "en_"
    root=Path(models_dir)
    if not root.is_dir():
        return []
    voices=[]
    for model in root.glob("*.onnx"):
        name=model.name[:-5]
        config=root/(model.name+".json")
        if not name.startswith(prefix) or not VOICE_NAME.fullmatch(name) or not config.is_file():
            continue
        try:
            meta=json.loads(config.read_text(encoding="utf-8-sig"))
            quality=str(meta.get("quality","unknown")).lower()
            length=model.stat().st_size
            if length<=0 or not isinstance(meta,dict):
                continue
        except (OSError,ValueError,TypeError):
            continue
        voices.append({"name":name,"quality":quality,"size_bytes":length,
                       "local_model":True,"voice_quality_not_audited":True})
    voices.sort(key=lambda a:(-QUALITY.get(a["quality"],0),a["name"]))
    return voices

def choose(models_dir:Path,language:str,requested:str|None=None)->str:
    candidates=available(models_dir,language)
    if requested:
        if not VOICE_NAME.fullmatch(requested):
            raise ValueError("invalid local Piper voice name")
        if requested not in {v["name"] for v in candidates}:
            raise ValueError("requested local Piper model and config are not installed")
        return requested
    if candidates:
        return candidates[0]["name"]
    # Explicit default remains backward-compatible, and actual synthesis will
    # fail if the user has not installed this model. No silent download.
    return "vi_VN-vais1000-medium" if language.startswith("vi") else "en_US-lessac-medium"
