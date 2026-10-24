#!/usr/bin/env python3
"""Read-only GA evidence gate. Never changes versions, GitHub releases or user media.

Source/package CI is necessary but insufficient. An independent Windows
render/audio/visual review must be documented before human GA authorization.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import release_manifest

NEEDED_TARGETS={30,60,90,180}
NEEDED_ASPECTS={"9:16","16:9"}

def evaluate(source:Path,windows_report:dict|None=None,review:dict|None=None)->dict:
    source_check=release_manifest.verify(source)
    pending=[]
    checks={"rc_source_manifest_verified":True,
            "independent_windows_pipeline_verified":False,
            "human_audio_visual_approval_verified":False}
    if windows_report is None:
        pending.append("MISSING_INDEPENDENT_WINDOWS_PIPER_REMOTION_FFMPEG_REPORT")
    else:
        profiles=windows_report.get("results",[])
        targets={x.get("target_seconds") for x in profiles if isinstance(x,dict)}
        rendered=(
            windows_report.get("schema")=="STAGE5_WINDOWS_LOCAL_ACCEPTANCE_V1"
            and windows_report.get("status")=="LOCAL_TECHNICAL_QA_PASS"
            and windows_report.get("real_piper_tts") is True
            and windows_report.get("remotion_rendered") is True
            and all(x.get("status")=="LOCAL_TECHNICAL_QA_PASS" and not x.get("issues")
                    and set(x.get("duration_seconds",{}))==NEEDED_ASPECTS
                    for x in profiles if isinstance(x,dict))
            and NEEDED_TARGETS.issubset(targets)
        )
        if not rendered:
            pending.append("INCOMPLETE_OR_FAILED_WINDOWS_FULL_PIPELINE_PROFILES")
        else:
            checks["independent_windows_pipeline_verified"]=True
    if review is None:
        pending.append("MISSING_HUMAN_INDEPENDENT_HOST_AND_MEDIA_REVIEW")
    else:
        assertions={
            "independent_windows_host":review.get("independent_windows_host") is True,
            "verified_video_listening_and_viewing":review.get("verified_video_listening_and_viewing") is True,
            "dual_ratio_safe_areas_reviewed":review.get("dual_ratio_safe_areas_reviewed") is True,
            "licensing_and_news_facts_reviewed":review.get("licensing_and_news_facts_reviewed") is True,
            "no_auto_posting":review.get("no_auto_posting") is True,
            "operator_approved_ga":review.get("operator_approved_ga") is True,
            "source_commit_matches":review.get("source_manifest_sha256")==source_check["manifest_sha256"],
            "reviewer_identity_recorded":bool(review.get("reviewer") and review.get("reviewed_at")),
        }
        if not all(assertions.values()):
            pending.extend("HUMAN_REVIEW_"+k.upper()+"_MISSING" for k,v in assertions.items() if not v)
        else:
            checks["human_audio_visual_approval_verified"]=True
    if not pending:
        state="ELIGIBLE_FOR_MANUAL_GA_RELEASE_REVIEW"
    else:
        state="RC_READY_WINDOWS_ACCEPTANCE_PENDING"
    return {"schema":"STAGE6_MANUAL_RELEASE_GATE_V1",
            "status":state,"version":source_check["version"],
            "source_manifest_sha256":source_check["manifest_sha256"],
            "windows_evidence_supplied":windows_report is not None,
            "human_review_supplied":review is not None,
            "checks":checks,"pending":pending,
            "ga_tag_created":False,"github_ga_release_published":False,
            "automatic_publication":False,
            "note":"Not a cryptographic attestation of the reviewer. Independent evidence and operator decision remain mandatory."}

def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",type=Path,default=Path(__file__).resolve().parents[1])
    ap.add_argument("--windows-report",type=Path)
    ap.add_argument("--human-review",type=Path)
    ap.add_argument("--report",type=Path)
    args=ap.parse_args()
    report=lambda p: json.loads(p.read_text(encoding="utf-8-sig")) if p else None
    try:
        answer=evaluate(args.source,report(args.windows_report),report(args.human_review))
        if args.report:
            if args.report.exists():
                raise FileExistsError("release gate report already exists")
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(answer,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(answer,ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError) as exc:
        ap.exit(2,"RELEASE_GATE_ERROR: "+str(exc)+"\n")

if __name__=="__main__":
    main()
