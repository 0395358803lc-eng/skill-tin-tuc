#!/usr/bin/env python3
"""Stage 5 production-adjacent performance report from REAL local benchmark evidence.

A parser cannot invent GPU measurements or render success. It only grades
finished benchmark JSON and exported QA results. Use Windows acceptance runner
to capture actual Piper/Remotion/FFmpeg metrics on the intended machine.
"""
from __future__ import annotations
import math

ASPECTS={"9:16","16:9"}
TARGETS={30,60,90,180}

def assess(measured:dict,qa:dict,target:int,requested_encoder:str)->dict:
    if target not in TARGETS or requested_encoder not in ("auto","cpu","nvenc"):
        raise ValueError("invalid acceptance profile")
    if not isinstance(measured,dict) or not isinstance(qa,dict):
        raise ValueError("missing measured benchmark or video QA")
    reasons=[]
    if measured.get("timeout") or measured.get("startup_stall_detected") or measured.get("returncode")!=0:
        reasons.append("PROCESS_FAILED_OR_TIMED_OUT")
    if measured.get("remotion_sample_every")!=1 or measured.get("native_motion_fps")!=30:
        reasons.append("NATIVE_30FPS_NOT_PROVEN")
    if measured.get("renderer_qa") is None:
        reasons.append("RENDERER_QA_MISSING")
    if qa.get("technical_pass") is not True or qa.get("errors"):
        reasons.append("TECHNICAL_QA_FAILED")
    if set(qa.get("formats",{}))!=ASPECTS:
        reasons.append("DUAL_ASPECT_MISSING")
    encoders=set()
    durations={}
    for ratio,entry in qa.get("formats",{}).items():
        if ratio not in ASPECTS:continue
        d=entry.get("duration_seconds")
        if type(d) not in (float,int) or not math.isfinite(d):
            reasons.append("VIDEO_DURATION_UNVERIFIED:"+ratio)
        else:
            durations[ratio]=float(d)
            if abs(d-target)>target*.05:
                reasons.append("VIDEO_DURATION_OUTSIDE_5PCT:"+ratio)
        renderer=measured.get("renderer_qa") or {}
        codec=((renderer.get("formats") or {}).get(ratio) or {}).get("encoder")
        if codec not in ("h264_nvenc","libx264"):
            reasons.append("ENCODER_NOT_MEASURED:"+ratio)
        else:
            encoders.add(codec)
        if requested_encoder=="cpu" and codec!="libx264":
            reasons.append("CPU_ENCODER_NOT_SELECTED:"+ratio)
        if requested_encoder=="nvenc" and codec!="h264_nvenc":
            reasons.append("NVENC_ENCODER_NOT_SELECTED:"+ratio)
    elapsed=measured.get("elapsed_seconds")
    rss=measured.get("peak_process_tree_rss_mb")
    if type(elapsed) not in (float,int) or elapsed<=0:
        reasons.append("WALL_CLOCK_TIME_NOT_MEASURED")
    if type(rss) not in (float,int) or rss<=0:
        reasons.append("PROCESS_RSS_NOT_MEASURED")
    if measured.get("sample_count",0)<1:
        reasons.append("RESOURCE_SAMPLES_MISSING")
    if not isinstance(measured.get("samples"),list):
        reasons.append("RESOURCE_SAMPLE_SERIES_MISSING")
    return {"schema":"STAGE5_LOCAL_PERFORMANCE_EVIDENCE_V1",
            "target_seconds":target,"requested_encoder":requested_encoder,
            "measured_encoders":sorted(encoders),
            "gpu_selected_for_both_aspects":encoders=={"h264_nvenc"} and not reasons,
            "cpu_selected_for_both_aspects":encoders=={"libx264"} and not reasons,
            "render_elapsed_seconds":elapsed,
            "process_rss_peak_mb":rss,
            "device_gpu_used_mb":measured.get("peak_gpu_used_mb"),
            "device_gpu_utilization_pct":measured.get("peak_gpu_util_pct"),
            "resource_note":"GPU figures from nvidia-smi are whole-device, not process exclusive.",
            "duration_seconds":durations,"issues":reasons,
            "status":"LOCAL_TECHNICAL_QA_PASS" if not reasons else "LOCAL_TECHNICAL_QA_FAIL",
            "human_listening_visual_media_rights_review_required":True,
            "independent_windows_acceptance_not_automatically_proven":True,
            "automatic_publication":False}
