#!/usr/bin/env python3
"""Independent Windows Stage 5 acceptance with locally installed Piper/Remotion/FFmpeg.

Do NOT run on production approved stories. Generates synthetic fixtures only,
renders full 30/60/90/180 profiles, records encoder/CPU/RAM/whole-GPU metrics,
and runs independent video, subtitles, audio and sampled-frame QA.
A successful automated run still requires a human to watch and listen.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import qa_engine
import stage15_duration_calibrate as calibration
import stage5_benchmark as benchmark
import stage5_perf_audit as performance

PROFILES=((30,"en-US"),(60,"vi-VN"),(90,"en-US"),(180,"vi-VN"))
ROOT=Path(__file__).resolve().parents[1]

def run(root:Path,encoder:str="auto",compare_cpu:bool=False,timeout:int=5400)->dict:
    root=root.resolve()
    if root.exists():
        raise FileExistsError("acceptance destination exists: never overwrite prior runs")
    if root==ROOT or root.is_relative_to(ROOT):
        raise ValueError("Windows benchmark destination must be outside the Skill")
    if encoder not in ("auto","cpu","nvenc") or timeout<600 or timeout>10800:
        raise ValueError("invalid benchmark encoder or timeout")
    root.mkdir(parents=True)
    results=[]
    for target,lang in PROFILES:
        key=f"{target:03d}s-{lang}"
        cal=calibration.calibrate(target,lang,root/("calibrate-"+key))
        if not cal["within_five_percent"]:
            raise RuntimeError("local Piper DEMO duration cannot be calibrated within 5%: "+key)
        input_path=Path(cal["manifest"])
        work=root/("render-"+key)
        metrics=benchmark.measure(input_path,work,encoder,
                     root/("benchmark-"+key+".json"),timeout=timeout,
                     sample_every=1,speech_rate=1.0,concurrency=1)
        report=qa_engine.analyze(work,root/("technical-qa-"+key+".json"),"both",frames=True)
        (root/("technical-qa-"+key+".json")).write_text(
            json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        accepted=performance.assess(metrics,report,target,encoder)
        (root/("perf-audit-"+key+".json")).write_text(
            json.dumps(accepted,ensure_ascii=False,indent=2),encoding="utf-8")
        results.append(accepted)
        if accepted["issues"]:
            raise RuntimeError("hardware/renderer QA FAILED for "+key+": "+str(accepted["issues"]))
    if compare_cpu and encoder!="cpu":
        target,lang=PROFILES[0]
        manifest=Path(calibration_file(root,target,lang))
        work=root/"render-cpu-comparison-030s"
        metrics=benchmark.measure(manifest,work,"cpu",
                    root/"benchmark-cpu-comparison-030s.json",timeout=timeout)
        qa=qa_engine.analyze(work,root/"technical-qa-cpu-030s.json","both",frames=True)
        (root/"technical-qa-cpu-030s.json").write_text(json.dumps(qa,indent=2),encoding="utf-8")
        checked=performance.assess(metrics,qa,target,"cpu")
        (root/"perf-audit-cpu-comparison-030s.json").write_text(
            json.dumps(checked,indent=2),encoding="utf-8")
        results.append(checked)
        if checked["issues"]:
            raise RuntimeError("CPU comparison failed: "+str(checked["issues"]))
    report={"schema":"STAGE5_WINDOWS_LOCAL_ACCEPTANCE_V1",
         "created_at":dt.datetime.now(dt.timezone.utc).isoformat(),
         "status":"LOCAL_TECHNICAL_QA_PASS",
         "profile_count":len(results),"results":results,
         "all_exports_synthetic_demo":True,
         "real_piper_tts":True,"remotion_rendered":True,
         "gpu_not_assumed":True,"human_video_and_licensing_review_still_required":True,
         "never_auto_publish":True,"release_ga_approved":False}
    (root/"stage5-windows-summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report

def calibration_file(root:Path,target:int,lang:str)->Path:
    return root/f"calibrate-{target:03d}s-{lang}"/"calibrated_demo.json"

def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--encoder",choices=("auto","cpu","nvenc"),default="auto")
    p.add_argument("--compare-cpu",action="store_true")
    p.add_argument("--timeout-per-render",type=int,default=5400)
    a=p.parse_args()
    report=run(a.out,a.encoder,a.compare_cpu,a.timeout_per_render)
    print(json.dumps({"status":report["status"],"profiles":report["profile_count"],
                      "human_final_review_required":True,"ga_approved":False}))
if __name__=="__main__":
    main()
