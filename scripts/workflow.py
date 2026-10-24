#!/usr/bin/env python3
"""Stage 13: restartable, human-gated news job controller for ChatGPT/Remote Desktop.
No source-reading, claim-writing, user consent, or approval is invented by this program.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import editorial_core as core
import news_editor as editor
import news_rss as rss
import qa_engine
import qa_repair
import duration_planner
import render_video as legacy
import job_integrity as integrity
import research_enrichment as research

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ.get("NEWS_SKILL_RUNTIME",ROOT.parent/(ROOT.name+"-runtime")))
DEFAULT_JOBS=RUNTIME/"jobs"
COUNTRIES=set(rss.COUNTRIES)
CATEGORIES=set(rss.CATEGORIES)
STAGES=("CREATED","AWAITING_EVIDENCE","NEEDS_EVIDENCE","AWAITING_SELECTION",
        "AWAITING_SCRIPT","AWAITING_APPROVAL","APPROVED","RENDERED",
        "TECHNICAL_QA_FAILED","TECHNICAL_QA_PASSED","AWAITING_HUMAN_FINAL_REVIEW")

def now()->str:return dt.datetime.now(dt.timezone.utc).isoformat()

# Stage16 uses identity-tagged lock; stale recovery is always explicit.
locked=integrity.lock_job
def filehash(f:Path)->str:return qa_engine.digest(f)
def read(f:Path)->dict:return json.loads(f.read_text(encoding="utf-8-sig"))

def checked_local_asset(job:Path, brief:dict, prefix:str)->Path|None:
    """Resolve and fingerprint only a local, approval-bound audio asset."""
    relative=brief.get(prefix+"_path")
    expected=brief.get(prefix+"_sha256")
    if relative is None and expected is None:
        if prefix=="music" and brief.get("music_license"):
            raise ValueError("unbound music license without approved media")
        return None
    if not isinstance(relative,str) or not relative.strip() or not isinstance(expected,str) or not re.fullmatch(r"[0-9a-fA-F]{64}",expected):
        raise ValueError(prefix+" requires approved relative path and SHA-256")
    p=Path(relative)
    if p.is_absolute() or ".." in p.parts or p==Path("."):
        raise ValueError(prefix+" must be a safe job-relative path")
    target=(job/p).resolve()
    if not target.is_relative_to(job.resolve()) or not target.is_file():
        raise ValueError(prefix+" must exist inside the job workspace")
    if filehash(target).lower()!=expected.lower():
        raise ValueError(prefix+" checksum differs from user-approved script")
    if prefix=="music":
        if not isinstance(brief.get("music_license"),str) or not brief["music_license"].strip():
            raise ValueError("music requires approved license evidence")
        if target.suffix.lower() not in (".wav",".mp3",".flac",".m4a",".ogg"):
            raise ValueError("unsupported background music format")
    else:
        if target.suffix.lower()!=".json":
            raise ValueError("pronunciation lexicon must be JSON")
        import narration_quality
        words=read(target)
        if not isinstance(words,dict):
            raise ValueError("pronunciation lexicon must contain a JSON object")
        narration_quality.lexicon_review(" ".join(s["narration"] for s in brief.get("stories",[])),words)
    return target
def write_once(p:Path,obj:dict)->None:
    integrity.json_new(p,obj)

def check_job(j:Path)->dict:
    j=j.resolve()
    if not j.is_dir() or not (j/"job.json").is_file():raise ValueError("job directory not initialized")
    meta=read(j/"job.json")
    if meta.get("schema_version")!=1 or meta.get("job_id")!=j.name:
        raise ValueError("malformed job metadata")
    return meta

def event(j:Path,step:str,details:dict|None=None)->None:
    log=j/"events.jsonl"
    row={"time":now(),"step":step,"details":details or {}}
    integrity.append_event(log,row)
    integrity.checkpoint(j,step,details)

def status(j:Path)->dict:
    meta=check_job(j)
    artifact_names=("candidates.json","queue.json","research_screening.json",
        "stage17_evidence_review.json","evidence.json","review.json",
        "selection.json","script.json","draft.json","duration_advisory.json","confirmation.json","approved.json",
        "render_result.json","technical_qa.json","technical_qa_recheck.json","technical_qa_recheck_02.json",
        "handoff.json","handoff_visual_revision.json")
    files={p:p in {x.name for x in j.iterdir()} for p in artifact_names}
    if files["approved.json"]:
        legacy.validate_brief(read(j/"approved.json"),False)
    latest=next((p for p in (j/"technical_qa_recheck_02.json",j/"technical_qa_recheck.json",j/"technical_qa.json") if p.exists()),j/"technical_qa.json")
    if latest.exists():
        qa=read(latest)
        stage="TECHNICAL_QA_PASSED" if qa.get("technical_pass") is True else "TECHNICAL_QA_FAILED"
    elif (j/"render_result.json").exists():stage="RENDERED"
    elif files["approved.json"]:stage="APPROVED"
    elif files["draft.json"]:stage="AWAITING_APPROVAL"
    elif files["selection.json"]:stage="AWAITING_SCRIPT"
    elif files["review.json"]:
        stage="AWAITING_SELECTION" if read(j/"review.json").get("eligible_count",0)>0 else "NEEDS_EVIDENCE"
    elif files["queue.json"]:stage="AWAITING_EVIDENCE"
    else:stage="CREATED"
    if files["handoff.json"]:stage="AWAITING_HUMAN_FINAL_REVIEW"
    instructions={
        "CREATED":"Run discover to retrieve unverified news candidates.",
        "AWAITING_EVIDENCE":"Agent must actually read original sources, build EVIDENCE.json and run evidence.",
        "NEEDS_EVIDENCE":"Insufficient evidence: start a new research job after source review.",
        "AWAITING_SELECTION":"Show sourced stories; wait for user's explicit selection, then run select.",
        "AWAITING_SCRIPT":"Write sourced script, link every claim and licensed asset; run draft.",
        "AWAITING_APPROVAL":"Show exact draft and SHA-256; wait for a NEW user approval.",
        "APPROVED":"Run render from approved.json; no independent script changes allowed.",
        "RENDERED":"Run qa for technical checks and bounded SRT repair.",
        "TECHNICAL_QA_FAILED":"Stop: inspect QA errors; no automatic publishing or unsupported repair.",
        "TECHNICAL_QA_PASSED":"Run handoff; human editorial/license review still required.",
        "AWAITING_HUMAN_FINAL_REVIEW":"Human must check freshness, claims, voice, visuals, and media rights before uploading manually."}
    state={"job_id":meta["job_id"],"stage":stage,"parameters":meta["parameters"],
           "artifacts":files,"job_directory":str(j),"next":instructions.get(stage)}
    state["recovery"]=integrity.recovery_plan(j)
    state["mutation_blocked"]=not state["recovery"]["safe_to_mutate"]
    if state["mutation_blocked"]:
        state["next"]="RECOVERY BLOCKED: inspect checkpoint/lock/unfinished attempt; never rerun or auto-approve."
    if files["handoff_visual_revision.json"]:
        final=read(j/"handoff_visual_revision.json")
        state["final_delivery_folder"]=final.get("delivery_folder")
        state["final_handoff_file"]=str(j/"handoff_visual_revision.json")
        state["note"]="Use the final delivery folder: the original handoff was superseded by a visual layout revision."
    return state

def init_job(args)->dict:
    params={"country":args.country,"category":args.category,"hours":args.hours,
            "language":args.language,"target_seconds":args.seconds,"aspect_ratio":args.aspect,
            "tone":args.tone}
    if params["country"] not in COUNTRIES or params["category"] not in CATEGORIES:
        raise ValueError("unsupported news category/country")
    if args.hours not in (6,24,72,168) or args.seconds not in (30,60,90,180):
        raise ValueError("time range outside supported news workflow choices")
    job_id=args.job_id or ("news-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")+"-"+uuid.uuid4().hex[:8])
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{5,75}",job_id):
        raise ValueError("unsafe job id")
    root=integrity.validate_jobs_root(args.jobs_root,ROOT)
    root.mkdir(parents=True,exist_ok=True)
    path=root/job_id
    path.mkdir(exist_ok=False)
    write_once(path/"job.json",{"schema_version":1,"job_id":job_id,"created_at":now(),
        "parameters":params,"human_gates":["SELECT_STORIES","APPROVE_EXACT_SCRIPT","REVIEW_BEFORE_PUBLICATION"],
        "publishing_integration":False})
    event(path,"INIT",params)
    return status(path)

def discover(j:Path)->dict:
    cfg=check_job(j)["parameters"]
    if (j/"candidates.json").exists() or (j/"queue.json").exists():
        raise ValueError("discovery exists; never overwrite, start a new job for new news window")
    feeds_path=ROOT/"examples"/"rss_sources.json"
    extra=[]
    if feeds_path.is_file():
        for feed in read_list(feeds_path):
            if feed.get("country","WORLD") not in (cfg["country"],"ALL"):continue
            feed_category=feed.get("category","general")
            if feed_category!=cfg["category"]:continue  # No generic headlines in targeted topic lists.
            extra.append({"name":feed["name"],"url":feed["url"]})
    result=rss.fetch(cfg["country"],cfg["category"],cfg["hours"],60,extra)
    write_once(j/"candidates.json",result)
    screening=research.group_rss(result,12)
    write_once(j/"research_screening.json",screening)
    shortlisted_ids={s["id"] for s in screening["shortlist"]}
    screened=dict(result)
    screened["candidates"]=[c for c in result["candidates"] if c["id"] in shortlisted_ids]
    screened["stage17_priority"]={s["id"]:s["discovery_priority_score"]
                                   for s in screening["shortlist"]}
    queue,markdown=editor.preview_candidates(screened,12)
    write_once(j/"queue.json",queue)
    integrity.atomic_new(j/"queue.md",(markdown+"\n").encode("utf-8"))
    event(j,"DISCOVER",{"candidates":len(queue["stories"]),"feed_status":result["feed_results"],
                        "screened_candidates":screening["total_candidates"],
                        "potential_event_groups":len(screening["possible_event_groups"]),
                        "factual_verification":False})
    return {"stage":"AWAITING_EVIDENCE","count":len(queue["stories"]),
            "queue_markdown":str(j/"queue.md"),"warning":"RSS is not fact verification. Agent must independently read articles and produce evidence."}

def read_list(path:Path)->list:
    x=json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(x,list):raise ValueError("RSS config must contain a list")
    return x

def checked_evidence(j:Path,source:Path)->dict:
    check_job(j)
    if not (j/"queue.json").exists():raise ValueError("discover must run first")
    if (j/"evidence.json").exists():raise ValueError("immutable evidence exists: start a new job to revise")
    bundle=read(source)
    report=core.check_bundle(bundle)
    cfg=check_job(j)["parameters"]
    enriched=research.research_review(bundle,report,cfg["hours"],cfg["country"])
    by_id={s["id"]:s for s in enriched["all_reviews"]}
    for item in report["story_reports"]:
        gate=by_id.get(item["id"],{})
        if not gate.get("eligible_for_human_editorial_review",False):
            item["eligible_for_human_editorial_review"]=False
            if gate.get("freshness_flags"):
                item["errors"].extend(gate["freshness_flags"])
            if gate.get("provenance_audit",{}).get("issues"):
                item["errors"].extend(gate["provenance_audit"]["issues"])
    report["eligible_count"]=sum(x["eligible_for_human_editorial_review"] for x in report["story_reports"])
    allowed={x["id"] for x in report["story_reports"] if x["eligible_for_human_editorial_review"]}
    report["editorial_ranking"]=[x for x in report["editorial_ranking"] if x["id"] in allowed]
    write_once(j/"evidence.json",bundle)
    write_once(j/"stage17_evidence_review.json",enriched)
    integrity.atomic_new(j/"stage17_evidence_review.md",(research.markdown(enriched)+"\n").encode("utf-8"))
    write_once(j/"review.json",report)
    integrity.atomic_new(j/"review.md",(editor.preview_evidence(bundle,report)+"\n").encode("utf-8"))
    event(j,"EVIDENCE",{"eligible":report["eligible_count"],"bundle_sha256":filehash(j/"evidence.json"),
        "verification_by_software":False})
    return {"stage":"AWAITING_SELECTION" if report["eligible_count"] else "NEEDS_EVIDENCE",
        "eligible":report["eligible_count"],"review":str(j/"review.md")}

def select_stories(j:Path,ids:list[str],message:str,at:str)->dict:
    if not (j/"review.json").is_file():raise ValueError("no evidence reviewed")
    if (j/"selection.json").exists():raise ValueError("selection already exists")
    selection=core.choose(read(j/"evidence.json"),read(j/"review.json"),ids,message,at)
    write_once(j/"selection.json",selection)
    event(j,"USER_SELECTION",{"ids":ids,"user_message":message})
    return {"stage":"AWAITING_SCRIPT","selected":ids}

def script_draft(j:Path,script_file:Path)->dict:
    if not (j/"selection.json").exists():raise ValueError("human selection must happen first")
    if (j/"draft.json").exists():raise ValueError("draft already exists")
    scripts=read(script_file)
    config=check_job(j)["parameters"]
    for field in ("country","category","language","aspect_ratio","target_seconds"):
        if scripts.get(field)!=config[field]:
            raise ValueError("script parameter differs from user's job request: "+field)
    bundle=read(j/"evidence.json");selection=read(j/"selection.json")
    # Stage17 never bypasses the user's selection or independent provenance checks.
    if (j/"stage17_evidence_review.json").is_file():
        inspected=research.research_review(bundle,core.check_bundle(bundle),check_job(j)["parameters"]["hours"])
        eligible={x["id"] for x in inspected["shortlist"] if x["eligible_for_human_editorial_review"]}
        if any(sid not in eligible for sid in selection["story_ids"]):
            raise ValueError("selected news has stale or non-independent claim evidence")
    # Enforce fresh structural evidence review before assembling an exact draft.
    rep=core.check_bundle(bundle)
    if any(not next((x["eligible_for_human_editorial_review"] for x in rep["story_reports"]
                     if x["id"]==sid),False) for sid in selection["story_ids"]):
        raise ValueError("selected story no longer passes evidence gate")
    for story in scripts.get('stories',[]):
        for scene in story.get('visual_plan',[]) or []:
            if scene.get('type') in ('licensed_image','licensed_broll'):
                asset=Path(scene.get('media_path',''))
                if not asset.name or asset.is_absolute() or '..' in asset.parts:
                    raise ValueError('licensed media must use safe relative path')
                candidate=(j/asset).resolve()
                if not candidate.is_relative_to(j.resolve()) or not candidate.is_file():
                    raise ValueError('licensed media must exist in the approved job workspace')
                if scene.get('media_sha256','').lower()!=filehash(candidate).lower():
                    raise ValueError('licensed media checksum is missing/incorrect')
    # Reject unlicensed or modified local audio BEFORE freezing the script hash.
    # Paths supplied in the candidate script are never allowed outside this job.
    for key in ("music","pronunciation_lexicon"):
        checked_local_asset(j,scripts,key)
    draft=core.draft_manifest(bundle,selection,scripts)
    guidance=duration_planner.predict([s["narration"] for s in draft["stories"]],
        draft["language"],draft["target_seconds"],1.0)
    write_once(j/"script.json",scripts)
    write_once(j/"draft.json",draft)
    write_once(j/"duration_advisory.json",guidance)
    event(j,"DRAFT",{"sha256":core.canonical_hash(draft),"stories":len(draft["stories"])})
    return {"stage":"AWAITING_APPROVAL","script_sha256":core.canonical_hash(draft),
            "draft_file":str(j/"draft.json"),"duration_advisory":guidance,
            "instruction":"Show exact draft and duration warning to user. Approval must be a NEW real user message."}

def approve(j:Path,confirmation:Path)->dict:
    if not (j/"draft.json").is_file():raise ValueError("no draft to approve")
    if (j/"approved.json").exists():raise ValueError("already approved")
    conf=read(confirmation)
    reviewed=core.approve_draft(read(j/"draft.json"),conf)
    legacy.validate_brief(reviewed,False)
    saved_confirmation=j/"confirmation.json"
    if saved_confirmation.exists():
        if read(saved_confirmation)!=conf:
            raise ValueError('recorded user confirmation differs from submitted approval')
    else:
        write_once(saved_confirmation,conf)
    write_once(j/"approved.json",reviewed)
    event(j,"USER_SCRIPT_APPROVAL",{"approved_hash":conf["script_sha256"],
                                   "story_count":len(reviewed["stories"])})
    return {"stage":"APPROVED","brief":str(j/"approved.json"),"aspect_ratio":reviewed["aspect_ratio"]}

def run_process(argv:list[str],env:dict,log:Path,timeout=2700)->tuple[int,str]:
    try:
        p=subprocess.run([str(x) for x in argv],env=env,stdout=subprocess.PIPE,
              stderr=subprocess.STDOUT,encoding="utf-8",errors="replace",timeout=timeout)
        txt=p.stdout
        code=p.returncode
    except subprocess.TimeoutExpired as e:
        txt="PROCESS_TIMEOUT "+str(e)
        code=124
    integrity.atomic_new(log,txt.encode("utf-8"))
    return code,txt

def render_job(j:Path,encoder:str="auto",speech_rate:float=1.,voice:str="")->dict:
    if not (j/"approved.json").exists():raise ValueError("user approval required")
    brief=read(j/"approved.json")
    legacy.validate_brief(brief,False)
    approved_music=checked_local_asset(j,brief,"music")
    approved_lexicon=checked_local_asset(j,brief,"pronunciation_lexicon")
    if (j/"technical_qa.json").exists():raise ValueError("QA exists: do not rerender an approved job")
    if not .75<=speech_rate<=1.35:raise ValueError("speech rate out of range")
    env=dict(os.environ,NEWS_SKILL_RUNTIME=str(RUNTIME),PIPER_VOICE_DIR=str(RUNTIME/"models"),
             PIPER_SPEECH_RATE=str(speech_rate),PYTHONIOENCODING="utf-8",
             PYTHONDONTWRITEBYTECODE="1")
    env["PATH"]=str(RUNTIME/"tools"/"ffmpeg-selected")+os.pathsep+env.get("PATH","")
    # No ambient workstation pronunciation map may affect a hashed brief.
    env.pop("PIPER_PRONUNCIATION_MAP",None)
    tried=[]
    for iteration,mode in enumerate(([encoder,"cpu"] if encoder!="cpu" else ["cpu"]),1):
        target=j/f"attempt-{iteration:02d}"
        if target.exists():raise ValueError("render attempt exists; do not overwrite: "+str(target))
        argv=[sys.executable,ROOT/"scripts"/"video_pipeline.py","--input",j/"approved.json",
              "--out",target,"--encoder",mode,"--speech-rate",str(speech_rate)]
        if voice:argv.extend(["--voice",voice])
        if approved_music:argv.extend(["--music",approved_music])
        if approved_lexicon:argv.extend(["--lexicon",approved_lexicon])
        code,output=run_process(argv,env,j/f"render-{iteration:02d}.log")
        tried.append({"attempt":iteration,"encoder":mode,"returncode":code,"output":str(target)})
        event(j,"RENDER_ATTEMPT",tried[-1])
        if code==0:
            if not (target/'qa_report.json').is_file():
                raise RuntimeError('render exited successfully without a technical manifest')
            exported=read(target/'qa_report.json')
            if exported.get('demo') or exported.get('status') not in ('TECHNICAL_PASS','NEEDS_EDITORIAL_TRIM') or Path(exported.get('source_manifest','')).resolve()!=(j/'approved.json').resolve():
                raise RuntimeError('render manifest mismatches approved input or is DEMO')
            if set(exported.get('formats',{}))!=(set(qa_engine.RATIOS) if brief['aspect_ratio']=='both' else {brief['aspect_ratio']}):
                raise RuntimeError('renderer missing requested aspect ratio')
            write_once(j/"render_result.json",{"directory":str(target),"attempts":tried,
                "approved_hash":filehash(j/"approved.json")})
            event(j,"RENDER_COMMITTED",{"output":str(target),"approved_hash":filehash(j/"approved.json")})
            return {"stage":"RENDERED","directory":str(target),"attempts":tried}
        if iteration==1 and encoder!="cpu":
            # Retry only errors clearly attributable to NVENC; never retry altered content,
            # missing licensed media, approval failure, or provenance errors.
            # A stray GPU keyword in a license/provenance error must never trigger
            # a second render. Only clearly attributable encoder/driver faults retry.
            disallowed=r"(?:copyright|licen[cs]e (?:missing|invalid|failed)|checksum|approved (?:media|script)|provenance|SHA-256)"
            gpu_fault=r"(?:NVENC (?:setup|init|initialization|encode|encoder|device|session|failed)|(?:Cannot load|Failed to load) libcuda|CUDA (?:driver|initialization|error)|No capable devices found|GPU requested|unsupported device)"
            if re.search(disallowed,output,re.I) or not re.search(gpu_fault,output,re.I):
                raise RuntimeError("render failure is not a recognized GPU fault; no automatic retry: "+output[-400:])
        else:
            raise RuntimeError("render failed; bounded attempts exhausted: "+output[-600:])
    raise RuntimeError("renderer failed")

def reconcile_render(j:Path)->dict:
    """Recover a COMPLETED render after a crash before render_result commit.

    No MP4 is rewritten, no user approval is invented; incomplete outputs stay blocked.
    """
    if (j/"render_result.json").exists():raise ValueError("render already committed; no overwrite")
    if not (j/"approved.json").is_file():raise ValueError("missing explicit script approval")
    approved=read(j/"approved.json")
    legacy.validate_brief(approved,False)
    attempts=sorted(x for x in j.glob("attempt-*") if x.is_dir())
    if not attempts or len(attempts)>2:
        raise ValueError("cannot reconcile without one or two bounded attempt folders")
    candidates=[]
    expected=set(qa_engine.RATIOS) if approved["aspect_ratio"]=="both" else {approved["aspect_ratio"]}
    for folder in attempts:
        metadata=folder/"qa_report.json"
        if not metadata.is_file():continue
        manifest=read(metadata)
        if manifest.get("demo") or manifest.get("status")!="TECHNICAL_PASS":
            continue
        if Path(manifest.get("source_manifest","")).resolve()!=(j/"approved.json").resolve():
            continue
        if set(manifest.get("formats",{}))!=expected:continue
        if not all((folder/row["file"]).is_file() for row in manifest["formats"].values()):
            continue
        candidates.append(folder)
    if len(candidates)!=1:
        raise ValueError("completed unique render not found; keep attempts for manual inspection")
    folder=candidates[0]
    diagnostic=j/"reconciled_render_qa.json"
    if diagnostic.exists():raise ValueError("reconciliation QA already exists")
    report=qa_engine.analyze(folder,diagnostic,approved["aspect_ratio"],False)
    integrity.json_new(diagnostic,report)
    if not report.get("technical_pass") or report.get("errors"):
        raise ValueError("recovered render failed independent QA")
    approved_hash=filehash(j/"approved.json")
    write_once(j/"render_result.json",{
        "directory":str(folder),"attempts":[{"attempt_folder":x.name} for x in attempts],
        "approved_hash":approved_hash,"recovered_after_interruption":True,
        "reconciliation_qa":str(diagnostic)})
    event(j,"RECOVER_RENDER",{"attempt_folder":folder.name,"approved_hash":approved_hash,
        "qa_technical_pass":True,"human_approval_unchanged":True})
    return {"stage":"RENDERED","directory":str(folder),"recovered":True,
            "approved_hash":approved_hash,"qa":str(diagnostic)}

def qa_job(j:Path,auto_repair:bool=True)->dict:
    if not (j/"render_result.json").is_file():raise ValueError("render a real approved brief first")
    if (j/"technical_qa.json").exists():raise ValueError("QA report exists, do not overwrite")
    record=read(j/"render_result.json")
    folder=Path(record["directory"]).resolve()
    if not folder.is_relative_to(j.resolve()) or not folder.is_dir():
        raise ValueError("render output must remain in this job")
    if record.get("approved_hash")!=filehash(j/"approved.json"):
        raise ValueError("approved brief changed after rendering")
    aspect=read(j/"approved.json")["aspect_ratio"]
    meta=read(folder/'qa_report.json')
    if meta.get('demo') or Path(meta.get('source_manifest','')).resolve()!=(j/'approved.json').resolve():
        raise ValueError('output is DEMO or not derived from exact approved brief')
    report=qa_engine.analyze(folder,j/"qa_initial.json",aspect,True)
    write_once(j/"qa_initial.json",report)
    repaired=False
    if report["errors"] and auto_repair and all(
        err.startswith(("MISSING_SRT:","INVALID_SRT:")) for err in report["errors"]):
        repaired_dir=j/"repaired-01"
        qa_repair.repair_srt_only(folder,repaired_dir,report)
        # Both QA runs are inspectable. The published bundle remains a separate copy.
        folder=repaired_dir
        report=qa_engine.analyze(folder,j/"technical_qa.json",aspect,True)
        repaired=True
    write_once(j/"technical_qa.json",report)
    write_once(j/"delivery_pointer.json",{"output_directory":str(folder),
        "approved_hash":filehash(j/"approved.json"),"repair_used":repaired})
    event(j,"TECHNICAL_QA",{"passed":report["technical_pass"],"errors":report["errors"],
                            "repair_used":repaired,"directory":str(folder)})
    return {"stage":"TECHNICAL_QA_PASSED" if report["technical_pass"] else "TECHNICAL_QA_FAILED",
            "technical_pass":report["technical_pass"],"qa":str(j/"technical_qa.json"),
            "output_directory":str(folder),"warnings":report["warnings"]}

def qa_recheck_job(j:Path)->dict:
    """At most two narrowly-scoped reruns for a missing external FFmpeg/ffprobe executable.
    Preserve the failed report; never alter approved content or video.
    """
    if (j/"technical_qa_recheck_02.json").exists():raise ValueError("second QA recheck exists; no further retries")
    original=j/"technical_qa_recheck.json" if (j/"technical_qa_recheck.json").exists() else j/"technical_qa.json"
    if not original.is_file():raise ValueError("first QA must exist")
    next_name="technical_qa_recheck_02.json" if original.name=="technical_qa_recheck.json" else "technical_qa_recheck.json"
    pointer_name="delivery_pointer_recheck_02.json" if original.name=="technical_qa_recheck.json" else "delivery_pointer_recheck.json"
    first=read(original)
    errors=first.get("errors",[])
    if first.get("technical_pass") or not errors or any(
        not re.fullmatch(r'MEDIA_QA_FAILURE:(?:9:16|16:9):\[WinError 2\] The system cannot find the file specified',str(e))
        for e in errors
    ):
        raise ValueError("QA recheck permitted only for missing external-tool executable errors")
    record=read(j/"render_result.json")
    if record.get("approved_hash")!=filehash(j/"approved.json"):
        raise ValueError("approved content changed")
    folder=Path(record["directory"]).resolve()
    if not folder.is_relative_to(j.resolve()) or first.get("folder")!=str(folder):
        raise ValueError("QA file points to another folder")
    approved=read(j/"approved.json")
    meta=read(folder/"qa_report.json")
    if meta.get("demo") or Path(meta.get("source_manifest","")).resolve()!=(j/"approved.json").resolve():
        raise ValueError("renderer output is DEMO or not the approved brief")
    checked=qa_engine.analyze(folder,j/next_name,approved["aspect_ratio"],True)
    write_once(j/next_name,checked)
    write_once(j/pointer_name,{
        "output_directory":str(folder),"approved_hash":filehash(j/"approved.json"),
        "repair_used":False,"original_failed_qa":str(original)})
    event(j,"TECHNICAL_QA_RECHECK",{"passed":checked["technical_pass"],
          "errors":checked["errors"],"previous_errors":errors,"output_directory":str(folder)})
    return {"stage":"TECHNICAL_QA_PASSED" if checked["technical_pass"] else "TECHNICAL_QA_FAILED",
        "technical_pass":checked["technical_pass"],"qa":str(j/next_name),
        "warnings":checked["warnings"],"errors":checked["errors"]}

def handoff(j:Path)->dict:
    if (j/"handoff.json").exists():raise ValueError("handoff already exists")
    qa_path=next((p for p in (j/"technical_qa_recheck_02.json",j/"technical_qa_recheck.json",j/"technical_qa.json") if p.exists()),j/"technical_qa.json")
    if not qa_path.is_file():raise ValueError("technical QA required")
    qa=read(qa_path)
    if not qa.get("technical_pass") or qa.get("demo"):
        raise ValueError("cannot handoff failed QA or DEMO")
    if qa.get("eligible_for_automatic_publication") is True:
        raise ValueError("unsupported auto publication")
    pointer_path=(
        j/"delivery_pointer_recheck_02.json" if qa_path.name=="technical_qa_recheck_02.json" else
        j/"delivery_pointer_recheck.json" if qa_path.name=="technical_qa_recheck.json" else
        j/"delivery_pointer.json")
    ptr=read(pointer_path)
    if ptr["approved_hash"]!=filehash(j/"approved.json"):
        raise ValueError("approved artifact was modified after QA")
    folder=Path(ptr["output_directory"])
    if not folder.resolve().is_relative_to(j.resolve()):
        raise ValueError("handoff output escaped job workspace")
    exported=[]
    for name in ["sources.json","publishing_metadata.json","media_rights.json",
                 "qa_report.json","narration.wav"]:
        path=folder/name
        if path.is_file():exported.append({"name":name,"path":str(path),"sha256":filehash(path)})
    for row in qa["formats"].values():
        video=folder/row["video"]
        if not video.is_file() or row.get("sha256")!=filehash(video):
            raise ValueError("MP4 content changed after technical QA")
        for name in [row["video"],"subtitles_"+("9x16" if row["width"]==1080 else "16x9")+".srt"]:
            path=folder/name
            if not path.is_file():raise ValueError("bundle incomplete: "+name)
            exported.append({"name":name,"path":str(path),"sha256":filehash(path)})
    hand={"status":"AWAITING_HUMAN_FINAL_REVIEW","job_id":j.name,
          "prepared_at":now(),"exports":exported,"report":str(qa_path),
          "warnings":qa["warnings"],"auto_uploaded":False,"ready_for_publication":False,
          "instructions":"Human must watch/listen, verify news freshness, all claims and media/music/voice licenses. User uploads manually."}
    write_once(j/"handoff.json",hand)
    event(j,"HANDOFF_PREPARED",{"files":len(exported),"autopost":False})
    return hand

def main()->None:
    ap=argparse.ArgumentParser(description="Gated, resumable AI-news jobs; user confirmation required")
    sub=ap.add_subparsers(dest="command",required=True)
    start=sub.add_parser("init")
    start.add_argument("--jobs-root",type=Path,default=DEFAULT_JOBS)
    start.add_argument("--job-id")
    start.add_argument("--country",default="US")
    start.add_argument("--category",default="general")
    start.add_argument("--hours",type=int,default=24)
    start.add_argument("--language",choices=["vi-VN","en-US","en-GB"],default="vi-VN")
    start.add_argument("--seconds",type=int,default=60)
    start.add_argument("--aspect",choices=["9:16","16:9","both"],default="both")
    start.add_argument("--tone",choices=["neutral","fast","in_depth"],default="neutral")
    for command_name in ["discover","evidence","select","draft","approve","render","qa","qa-recheck","handoff","status","resume","recover-lock","reconcile-render"]:
        a=sub.add_parser(command_name);a.add_argument("--job",type=Path,required=True)
        if command_name in ("evidence","draft"):a.add_argument("--file",type=Path,required=True)
        if command_name=="approve":a.add_argument("--confirmation",type=Path,required=True)
        if command_name=="select":
            a.add_argument("--ids",required=True)
            a.add_argument("--user-message",required=True)
            a.add_argument("--confirmed-at",required=True)
        if command_name=="render":
            a.add_argument("--encoder",choices=["auto","cpu","nvenc"],default="auto")
            a.add_argument("--speech-rate",type=float,default=1.)
            a.add_argument("--voice",default="")
        if command_name=="qa":a.add_argument("--no-repair",action="store_true")
    o=ap.parse_args()
    try:
        if o.command=="init":result=init_job(o)
        else:
            j=o.job.resolve();check_job(j)
            if o.command=='status':result=status(j)
            elif o.command=='resume':
                result=status(j)
                result['read_only']=True
                result['requires_manual_reconciliation']=not result['recovery']['safe_to_mutate']
            elif o.command=='recover-lock':
                result=integrity.recover_stale_lock(j)
            else:
                # Always gate mutation against the checkpoint/lock/attempt ledger.
                # Recovery exception is narrow and must still pass video/approval QA.
                integrity.assert_action_allowed(j,o.command)
                with locked(j):
                    if o.command=='discover':result=discover(j)
                    elif o.command=='evidence':result=checked_evidence(j,o.file)
                    elif o.command=='select':result=select_stories(j,[x.strip() for x in o.ids.split(',') if x.strip()],o.user_message,o.confirmed_at)
                    elif o.command=='draft':result=script_draft(j,o.file)
                    elif o.command=='approve':result=approve(j,o.confirmation)
                    elif o.command=='render':result=render_job(j,o.encoder,o.speech_rate,o.voice)
                    elif o.command=='reconcile-render':result=reconcile_render(j)
                    elif o.command=='qa':result=qa_job(j,not o.no_repair)
                    elif o.command=='qa-recheck':result=qa_recheck_job(j)
                    elif o.command=='handoff':result=handoff(j)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,OSError,RuntimeError,KeyError,TypeError,subprocess.TimeoutExpired,json.JSONDecodeError) as e:
        ap.exit(2,"WORKFLOW_ERROR: "+str(e)+"\n")
if __name__=="__main__":main()
