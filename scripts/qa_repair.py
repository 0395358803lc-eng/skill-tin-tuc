#!/usr/bin/env python3
"""Conservative repair: regenerate deterministic SRT sidecars from saved Remotion cues.
Never rewrite audio, video, evidence, or approvals. Never modify original render folder.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import qa_engine
import render_video

def repair_srt_only(folder:Path,target:Path,qa_report:dict)->dict:
    folder=folder.resolve();target=target.resolve()
    if target.exists():raise ValueError("repair target exists, cannot overwrite")
    if not folder.is_dir() or target.is_relative_to(folder):
        raise ValueError("repair target must be a separate empty/nonexistent directory")
    errors=qa_report.get("errors",[])
    if not errors:raise ValueError("no repair required")
    if any(not str(e).startswith(("MISSING_SRT:","INVALID_SRT:")) for e in errors):
        raise ValueError("non-repairable errors; stop and return to responsible stage")
    if qa_report.get("folder")!=str(folder):
        raise ValueError("QA report belongs to another output folder")
    metadata=json.loads((folder/"qa_report.json").read_text(encoding="utf-8-sig"))
    formats=metadata["formats"]
    fixes={}
    for error in errors:
        aspect=next((a for a in qa_engine.RATIOS if error.startswith(('MISSING_SRT:'+a,'INVALID_SRT:'+a+':'))),None)
        if aspect not in qa_engine.RATIOS or aspect not in formats:
            raise ValueError("unrecognized aspect in QA report")
        suffix=qa_engine.RATIOS[aspect][2]
        file=folder/"_work"/f"props-{suffix}.json"
        if not file.is_file():raise ValueError("renderer cue source is absent; rerender required")
        props=json.loads(file.read_text(encoding="utf-8-sig"))
        cues=props.get("cues")
        if not isinstance(cues,list) or not cues:raise ValueError("no authoritative saved cues")
        duration=float(metadata.get("duration_seconds",0))
        entries=[]
        for cue in cues:
            if not isinstance(cue,dict):
                raise ValueError("cue must be an object")
            a,b,t=cue.get("start"),cue.get("end"),cue.get("text")
            if not isinstance(a,(float,int)) or not isinstance(b,(float,int)) or not isinstance(t,str):
                raise ValueError("invalid cue type")
            if not (0<=a<b<=duration+.25) or not t.strip():
                raise ValueError("saved cue is invalid/outside video duration")
            entries.append((a,b,t))
        fixes[aspect]=(suffix,entries)
    target.mkdir(parents=True,exist_ok=False)
    try:
        # Copy only published outputs and package artifacts, not huge source intermediate video.
        for f in folder.iterdir():
            if f.is_symlink():raise ValueError("symlink in bundle is forbidden")
            if f.is_file():
                shutil.copy2(f,target/f.name)
        (target/"_work").mkdir()
        for aspect,(suffix,cues) in fixes.items():
            original=folder/"_work"/f"props-{suffix}.json"
            shutil.copy2(original,target/"_work"/original.name)
            final=target/f"subtitles_{suffix}.srt"
            # Saved cue text and timing came from renderer; this is a mechanical repair.
            render_video.write_srt(cues,final)
            qa_engine.verify_srt(final,float(metadata["duration_seconds"]))
        audit={"repair_version":1,"repair_time":dt.datetime.now(dt.timezone.utc).isoformat(),
               "source_dir":str(folder),"source_qa":qa_report.get("checked_at"),
               "changes":["REGENERATE_SRT:"+k for k in sorted(fixes)],
               "script_and_video_unchanged":True,"requires_new_qa":True,
               "note":"No source video, approved narration, rights or script changed."}
        (target/"repair_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    except Exception:
        # Preserve partial files for debugging rather than delete user data; target remains not approved.
        raise
    return audit

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--folder",required=True,type=Path)
    ap.add_argument("--qa",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    opt=ap.parse_args()
    try:
        report=json.loads(opt.qa.read_text(encoding="utf-8-sig"))
        result=repair_srt_only(opt.folder,opt.out,report)
        print(json.dumps({"status":"REPAIRED_REQUIRES_FRESH_QA",
                          "output":str(opt.out),"changes":result["changes"]},ensure_ascii=False))
    except (ValueError,OSError,KeyError,TypeError,IndexError) as exc:
        ap.exit(2,"REPAIR_ERROR: "+str(exc)+"\n")
if __name__=="__main__":main()
