#!/usr/bin/env python3
"""GitHub CI FFmpeg smoke: synthetic 30/60/90/180-second 9:16 + 16:9 H264/AAC.

This is an actual decode/probe/SRT/audio/frame QA test of LOOPED color+tone,
NOT a Remotion render, Piper voice, human visual evaluation, or production news.
Output stays outside the source repository and is never published.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import qa_engine as qa

DURATIONS=(30,60,90,180)
FORMATS={"9:16":(1080,1920,"9x16"),"16:9":(1920,1080,"16x9")}

def execute(cmd:list[str],timeout:int=180)->None:
    p=subprocess.run([str(c) for c in cmd],capture_output=True,text=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError("synthetic FFmpeg test failed: "+(p.stderr or p.stdout)[-800:])

def stamp(seconds:float)->str:
    ms=round(seconds*1000)
    hours,ms=divmod(ms,3600000)
    minutes,ms=divmod(ms,60000)
    sec,ms=divmod(ms,1000)
    return f"{hours:02d}:{minutes:02d}:{sec:02d},{ms:03d}"

def srt(duration:int)->str:
    lines=[]
    for i,start in enumerate(range(0,duration,5),1):
        end=min(duration,start+4.9)
        lines.append(f"{i}\n{stamp(start)} --> {stamp(end)}\n"
                     "DEMO synthetic media validation - not real news\n")
    return "\n".join(lines)

def create_seed(ffmpeg:str,output:Path,width:int,height:int)->None:
    execute([ffmpeg,"-hide_banner","-loglevel","error","-f","lavfi","-i",
        f"color=c=0x27436a:s={width}x{height}:r=30",
        "-f","lavfi","-i","sine=frequency=640:sample_rate=48000",
        "-t","2","-shortest","-c:v","libx264","-preset","ultrafast",
        "-pix_fmt","yuv420p","-c:a","aac","-b:a","96k",
        "-movflags","+faststart",output],timeout=120)

def fixture(folder:Path,seeds:dict[str,Path],duration:int,ffmpeg:str)->None:
    folder.mkdir()
    exports={}
    for aspect,(_w,_h,suffix) in FORMATS.items():
        name=f"DEMO_DO_NOT_PUBLISH_{suffix}.mp4"
        final=folder/name
        execute([ffmpeg,"-hide_banner","-loglevel","error","-stream_loop","-1",
            "-i",seeds[aspect],"-t",str(duration),"-map","0:v:0","-map","0:a:0",
            "-c","copy","-avoid_negative_ts","make_zero",final],timeout=100)
        exports[aspect]={"file":name}
        (folder/f"subtitles_{suffix}.srt").write_text(srt(duration),encoding="utf-8")
    (folder/"qa_report.json").write_text(json.dumps({
        "status":"TECHNICAL_PASS","demo":True,
        "target_seconds":duration,"duration_seconds":duration,
        "formats":exports,"Piper_TTS":False,
        "remotion_frame_sampling_step":1,
        "motion_quality":"SYNTHETIC_2S_STREAM_REPEAT_NOT_PRODUCTION",
        "source_manifest":"synthetic-smoke-no-approved-script",
        "synthetic_footage_repeat":True,"remotion_executed":False
    },indent=2),encoding="utf-8")
    (folder/"sources.json").write_text(json.dumps([{"headline":"Fictional-only media QA",
        "sources":[{"title":"Synthetic A","url":"https://example.org/demo"},
                   {"title":"Synthetic B","url":"https://example.net/demo"}]}]),encoding="utf-8")
    (folder/"publishing_metadata.json").write_text(json.dumps({
        "title":"DEMO - NOT REAL NEWS","description":"Synthetic media only", "hashtags":[]
    }),encoding="utf-8")
    (folder/"media_rights.json").write_text(json.dumps({
        "rights_status":"REVIEW_REQUIRED_BEFORE_PUBLICATION",
        "media":[],"music_license":None
    }),encoding="utf-8")
    # Placeholder to satisfy structural artifact check, NOT a narration recording.
    with wave.open(str(folder/"narration.wav"),"wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\0"*16000*2)

def run(out:Path,ffmpeg:str="ffmpeg",ffprobe:str="ffprobe")->dict:
    out=out.resolve()
    root=Path(__file__).resolve().parents[1]
    if out==root or out.is_relative_to(root):
        raise ValueError("smoke output must be outside the source Skill directory")
    if out.exists():
        raise FileExistsError("smoke output exists; refuse to overwrite")
    if not shutil.which(ffmpeg) or not shutil.which(ffprobe):
        raise RuntimeError("FFmpeg and FFprobe must be installed on the CI host")
    out.mkdir(parents=True)
    seeds={}
    for aspect,(width,height,suffix) in FORMATS.items():
        path=out/f"_synthetic_seed_{suffix}.mp4"
        create_seed(ffmpeg,path,width,height)
        seeds[aspect]=path
    cases=[]
    for duration in DURATIONS:
        folder=out/f"demo-{duration}s-both"
        fixture(folder,seeds,duration,ffmpeg)
        qa_report=out/f"technical-qa-{duration}s.json"
        report=qa.analyze(folder,qa_report,"both",frames=True)
        qa_report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        checked={aspect:round(data["duration_seconds"],2) for aspect,data in report["formats"].items()}
        if set(checked)!=set(FORMATS) or any(abs(x-duration)>1 for x in checked.values()):
            raise RuntimeError(f"synthetic matrix duration/aspect mismatch: {duration} {checked}")
        if not report["technical_pass"]:
            raise RuntimeError(f"synthetic media QA FAILED for {duration}s: {report['errors']}")
        cases.append({"target_seconds":duration,"measured_seconds":checked,
                      "technical_pass":True,"warnings":report["warnings"],
                      "video_sha256":{aspect:data["sha256"] for aspect,data in report["formats"].items()}})
    result={"schema":"STAGE5_SYNTHETIC_MEDIA_QA_V1",
        "created_at":dt.datetime.now(dt.timezone.utc).isoformat(),
        "status":"SYNTHETIC_MEDIA_QA_PASS","cases":cases,
        "outputs_checked":len(cases)*len(FORMATS),
        "synthetic_two_second_clip_repeated":True,
        "remotion_rendered":False,"piper_used":False,"gpu_benchmarked":False,
        "windows_independent_acceptance":False,"auto_published":False,
        "note":"Tests actual FFmpeg MP4 format, SRT, waveform, sampled frames and duration only. "
               "Not evidence of good speech, music, scene changes, real event fact checking or GA."}
    (out/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    return result

def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--ffmpeg",default="ffmpeg")
    parser.add_argument("--ffprobe",default="ffprobe")
    args=parser.parse_args()
    result=run(args.out,args.ffmpeg,args.ffprobe)
    print(json.dumps({"status":result["status"],"outputs_checked":result["outputs_checked"],
                      "durations":[x["target_seconds"] for x in result["cases"]],
                      "real_remotion_qa":False,"real_gpu_qa":False}))
if __name__=="__main__":
    main()
