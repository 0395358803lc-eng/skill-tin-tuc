#!/usr/bin/env python3
"""Stage 12: inspect real exported MP4/SRT; structural QA is not editorial fact checking."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

RATIOS={"9:16":(1080,1920,"9x16"),"16:9":(1920,1080,"16x9")}

def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):h.update(part)
    return h.hexdigest()

def command(args:list[str], timeout=180)->str:
    skill=Path(__file__).resolve().parents[1]
    runtime=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(skill.parent/(skill.name+'-runtime'))))
    tools=runtime/'tools'/'ffmpeg-selected'
    env=dict(os.environ)
    if tools.is_dir():env['PATH']=str(tools)+os.pathsep+env.get('PATH','')
    argv=[str(x) for x in args]
    if argv and argv[0].lower() in ('ffmpeg','ffprobe'):
        resolved=tools/(argv[0]+'.exe')
        if resolved.is_file():
            argv[0]=str(resolved)  # Windows CreateProcess cannot use a child-only PATH for lookup.
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                     encoding="utf-8",errors="replace",timeout=timeout,env=env)
    if p.returncode:
        raise RuntimeError(f"external tool exited {p.returncode}: {p.stdout[-1400:]}")
    return p.stdout

def probe(path:Path)->dict:
    return json.loads(command(["ffprobe","-v","error","-show_streams","-show_format","-of","json",path]))

def srt_time(value:str)->float:
    match=re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})",value)
    if not match:raise ValueError("invalid SRT timestamp "+value)
    a,b,c,d=map(int,match.groups())
    if b>59 or c>59:raise ValueError("invalid SRT time units")
    return 3600*a+60*b+c+d/1000

def verify_srt(path:Path,seconds:float)->dict:
    raw=path.read_text(encoding="utf-8-sig")
    blocks=[x.strip() for x in re.split(r"\r?\n\s*\r?\n",raw.strip()) if x.strip()]
    if not blocks:raise ValueError("SRT has no cues")
    previous=0.
    covered=0.
    longest_chars=0
    count=0
    for block in blocks:
        lines=block.splitlines()
        if len(lines)<3 or not lines[0].strip().isdigit() or int(lines[0])!=count+1:
            raise ValueError("SRT invalid numbering/text")
        match=re.fullmatch(r"(.+?)\s+-->\s+(.+)",lines[1].strip())
        if not match:raise ValueError("SRT missing timeline arrow")
        start,end=srt_time(match[1]),srt_time(match[2])
        if not start>=previous-.06 or end<=start or end>seconds+.25:
            raise ValueError("SRT overlapping/out of bounds cue")
        if not " ".join(lines[2:]).strip():raise ValueError("SRT empty text")
        covered+=end-start
        longest_chars=max(longest_chars,len(' '.join(lines[2:])))
        previous=end
        count+=1
    return {"cues":count,"last_end_seconds":round(previous,3),"non_overlapping":True,
            "caption_coverage_ratio":round(covered/max(seconds,0.001),3),
            "longest_cue_characters":longest_chars}

def audio_scan(path:Path)->dict:
    # ffmpeg volumedetect and silencedetect analyze audio without editing the source.
    raw=command(["ffmpeg","-hide_banner","-nostats","-i",path,
        "-vn","-af","volumedetect,silencedetect=noise=-43dB:d=1.5",
        "-f","null","-"],timeout=450)
    peak=re.findall(r"max_volume:\s*(-?[\d.]+)\s+dB",raw)
    mean=re.findall(r"mean_volume:\s*(-?[\d.]+)\s+dB",raw)
    silence=[float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)",raw)]
    return {"peak_dB":float(peak[-1]) if peak else None,
            "mean_dB":float(mean[-1]) if mean else None,
            "silence_segments_over_1_5s":len(silence),
            "longest_silence_seconds":round(max(silence,default=0.),2)}

def preview_points(duration:float,props_path:Path|None=None)->list[tuple[str,float]]:
    """Sample every editorial story midpoint, plus non-boundary checkpoints."""
    proposed=[('timeline_12pct',duration*.12),('timeline_51pct',duration*.51),
              ('timeline_87pct',duration*.87)]
    if props_path and props_path.is_file():
        try:
            data=json.loads(props_path.read_text(encoding='utf-8-sig'))
            cursor=0
            for i,story in enumerate(data.get('stories',[])[:15],1):
                frames=story.get('durationFrames')
                if not isinstance(frames,int) or frames<=0:continue
                proposed.append((f'story_{i:02d}_middle',(cursor+frames/2)/30))
                cursor+=frames
        except (OSError,ValueError,TypeError,AttributeError):
            pass
    unique=[]
    # Retain each story midpoint first; percentage checkpoints are only supplemental.
    for label,second in sorted(proposed,key=lambda z:(not z[0].startswith('story_'),z[1])):
        second=round(max(.05,min(duration-.05,second)),2)
        if label.startswith('story_') or not any(abs(second-seen)<.35 for _,seen in unique):
            unique.append((label,second))
    return sorted(unique,key=lambda z:z[1])

def previews(path:Path,duration:float,out_dir:Path,props_path:Path|None=None)->list[dict]:
    out_dir.mkdir(parents=True,exist_ok=False)
    points=preview_points(duration,props_path)
    outputs=[]
    for i,(label,sec) in enumerate(points,1):
        target=out_dir/f"frame_{i:02d}.jpg"
        command(["ffmpeg","-hide_banner","-loglevel","error","-ss",str(sec),"-i",path,
                "-frames:v","1","-vf","scale=480:-2", "-q:v","4",target],timeout=90)
        with Image.open(target) as img:
            gray=img.convert("L").resize((80,80))
            pixels=list(gray.get_flattened_data() if hasattr(gray,'get_flattened_data') else gray.getdata())
            mean=sum(pixels)/len(pixels)
            dynamic=max(pixels)-min(pixels)
        outputs.append({"label":label,"second":sec,"filename":str(target),
                        "mean_luma":round(mean,1),"dynamic_range":dynamic,
                        "near_black":mean<8 and dynamic<20})
    return outputs

def analyze(folder:Path,report_path:Path,expected_aspect:str|None=None,
            frames:bool=True)->dict:
    folder=folder.resolve()
    if not folder.is_dir():raise ValueError("output folder not found")
    baseline=folder/"qa_report.json"
    if not baseline.is_file():raise ValueError("renderer QA manifest missing")
    source=json.loads(baseline.read_text(encoding="utf-8-sig"))
    if source.get("status") not in ("TECHNICAL_PASS","NEEDS_EDITORIAL_TRIM"):
        raise ValueError("renderer QA manifest not technically passed")
    declared=source.get("formats",{})
    if not isinstance(declared,dict) or not declared:raise ValueError("no declared formats")
    if expected_aspect and set(declared)!=(set(RATIOS) if expected_aspect=="both" else {expected_aspect}):
        raise ValueError("output does not contain exact expected aspect list")
    warnings=[]; errors=[]; detail={}
    for aspect, entry in declared.items():
        if aspect not in RATIOS or not isinstance(entry,dict):
            errors.append("UNSUPPORTED_ASPECT:"+str(aspect));continue
        width,height,suffix=RATIOS[aspect]
        name=entry.get("file","")
        if not name or Path(name).name!=name:
            errors.append("UNSAFE_FILENAME:"+str(aspect));continue
        video=folder/name
        captions=folder/f"subtitles_{suffix}.srt"
        if not video.is_file() or video.stat().st_size<1000:
            errors.append("MISSING_VIDEO:"+aspect);continue
        try:
            metadata=probe(video)
            stream=metadata.get("streams",[])
            video_stream=[v for v in stream if v.get("codec_type")=="video"]
            audio_stream=[a for a in stream if a.get("codec_type")=="audio"]
            if len(video_stream)!=1 or len(audio_stream)!=1:
                raise ValueError("expected exactly one video and one audio stream")
            v,a=video_stream[0],audio_stream[0]
            seconds=float(metadata["format"]["duration"])
            assert seconds>0 and math.isfinite(seconds)
            if (v.get("width"),v.get("height"))!=(width,height):
                raise ValueError("resolution mismatch")
            if v.get("codec_name")!="h264" or a.get("codec_name")!="aac":
                raise ValueError("codec mismatch")
            rate=v.get("avg_frame_rate","0/1").split("/")
            if len(rate)!=2 or abs(float(rate[0])/float(rate[1])-30)>.1:
                raise ValueError("frame rate not 30 FPS")
            if abs(seconds-float(source.get("duration_seconds",0)))>1.0:
                raise ValueError("duration differs from renderer timing")
            target=float(source.get('target_seconds',0))
            if seconds>target+5.0:
                errors.append('OVER_TARGET_DURATION:'+aspect)
            if source.get('demo') is not True and target>0 and abs(seconds-target)>target*.05:
                errors.append('REAL_DURATION_OUTSIDE_5PCT:'+aspect)
            if seconds<target*.90:
                warnings.append('VIDEO_UNDER_TARGET_EDITORIAL_REVIEW:'+aspect)
            if not captions.is_file():
                errors.append("MISSING_SRT:"+aspect)
                caption_result=None
            else:
                try:
                    caption_result=verify_srt(captions,seconds)
                    if caption_result['caption_coverage_ratio']<.60:
                        warnings.append('LOW_CAPTION_COVERAGE_REVIEW:'+aspect)
                    if caption_result.get('longest_cue_characters',0)>(65 if aspect=='9:16' else 82):
                        warnings.append('STAGE18_LONG_CAPTION_SAFE_ZONE_REVIEW:'+aspect)
                except (ValueError,OSError) as e:
                    errors.append("INVALID_SRT:"+aspect+":"+str(e));caption_result=None
            sound=audio_scan(video)
            if sound["peak_dB"] is None or sound["mean_dB"] is None or sound["mean_dB"]<-48:
                errors.append("MUTED_OR_MISSING_AUDIO:"+aspect)
            if sound["longest_silence_seconds"]>max(4.,seconds*.4):
                warnings.append("PROLONGED_SILENCE_REVIEW:"+aspect)
            props_path=folder/"_work"/f"props-{suffix}.json"
            sampled=previews(video,seconds,report_path.parent/(report_path.stem+"_frames")/suffix,props_path) if frames else []
            if any(x["near_black"] for x in sampled):
                warnings.append("POSSIBLE_BLACK_FRAME:"+aspect)
            detail[aspect]={"video":name,"sha256":digest(video),
                            "bytes":video.stat().st_size,"duration_seconds":seconds,
                            "width":width,"height":height,"fps":30,
                            "audio":sound,"subtitles":caption_result,
                            "preview_frames":sampled}
        except (RuntimeError,ValueError,ZeroDivisionError,KeyError,AssertionError,OSError,subprocess.TimeoutExpired) as e:
            errors.append("MEDIA_QA_FAILURE:"+aspect+":"+str(e))
    required=["sources.json","publishing_metadata.json","narration.wav"]
    for item in required:
        if not (folder/item).is_file():errors.append("MISSING_DELIVERY_FILE:"+item)
    # Stage21 editorial handoff warning: do not silently rewrite user-approved metadata.
    metadata_path=folder/'publishing_metadata.json'
    if metadata_path.is_file() and source.get('demo') is not True:
        try:
            meta=json.loads(metadata_path.read_text(encoding='utf-8-sig'))
            description=str(meta.get('description','')).lower()
            if 'bản nháp chờ người dùng phê duyệt' in description or 'awaiting user approval' in description:
                warnings.append('PUBLISHING_METADATA_STILL_SAYS_DRAFT_HUMAN_REVIEW_REQUIRED')
        except (ValueError,TypeError,OSError):
            errors.append('INVALID_PUBLISHING_METADATA')
    if (folder/'sources.json').is_file():
        try:
            packages=json.loads((folder/'sources.json').read_text(encoding='utf-8-sig'))
            if not isinstance(packages,list) or not packages:
                raise ValueError('empty source ledger')
            for item in packages:
                if not isinstance(item,dict) or len(item.get('sources',[]))<2:
                    raise ValueError('every story needs >=2 sources')
                if source.get('demo') is not True:
                    for ref in item['sources']:
                        host=urlparse(ref.get('url','')).hostname or ''
                        if host.lower() in ('example.com','example.org','example.net') or host.lower().endswith('.example'):
                            errors.append('PLACEHOLDER_SOURCE_URL')
        except (ValueError,TypeError,OSError,AttributeError) as e:
            errors.append('INVALID_SOURCE_LEDGER:'+str(e))
    # Stage20 design audit: backwards-compatible with previous deliveries.
    if source.get('stage20_design_qa'):
        name=str(source['stage20_design_qa'])
        visual_path=folder/name
        if name!='visual_design.json' or not visual_path.is_file():
            errors.append('STAGE20_VISUAL_DESIGN_MISSING_OR_UNSAFE')
        else:
            try:
                import studio_design
                visual=json.loads(visual_path.read_text(encoding='utf-8-sig'))
                if visual.get('schema')!='STAGE20_DESIGN_V1' or visual.get('visual_style')!=source.get('stage20_visual_style'):
                    errors.append('STAGE20_VISUAL_DESIGN_STYLE_MISMATCH')
                if visual.get('human_visual_review_required') is not True:
                    errors.append('STAGE20_HUMAN_REVIEW_FLAG_INVALID')
                if visual.get('identity_assets_external') is not False:
                    errors.append('STAGE20_IDENTITY_REQUIRES_EXTERNAL_ASSETS')
                areas=visual.get('safe_areas',{})
                vertical=areas.get('9:16',{})
                horizontal=areas.get('16:9',{})
                if (vertical.get('width')!=1080 or vertical.get('height')!=1920 or
                    horizontal.get('width')!=1920 or horizontal.get('height')!=1080 or
                    vertical.get('subtitle_bottom',0)<350 or horizontal.get('subtitle_bottom',0)<145 or
                    vertical.get('left_guard',0)<70 or horizontal.get('left_guard',0)<95):
                    errors.append('STAGE20_SAFE_AREAS_INVALID')
                if vertical.get('content_max_y',9999)>1320:
                    warnings.append('STAGE20_OLDER_SAFE_AREA_METADATA_REVIEW')
                for note in visual.get('warnings',[]):
                    warnings.append('STAGE20_LAYOUT_REVIEW:'+str(note.get('code')))
                for ratio in declared:
                    suffix='9x16' if ratio=='9:16' else '16x9'
                    props_file=folder/'_work'/('props-'+suffix+'.json')
                    if props_file.is_file():
                        props=json.loads(props_file.read_text(encoding='utf-8-sig'))
                        if (props.get('visualStyle')!=visual.get('visual_style') or
                            props.get('language')!=visual.get('language')):
                            errors.append('STAGE20_PROPS_BRIEF_MISMATCH:'+ratio)
                    else:
                        warnings.append('STAGE20_PROPS_NOT_RETAINED_REVIEW:'+ratio)
            except (OSError,TypeError,ValueError,KeyError) as exc:
                errors.append('STAGE20_VISUAL_DESIGN_INVALID')
    # Stage18/19 sidecar validation remains backwards-compatible with legacy deliveries.
    if source.get('stage18_voice_qa'):
        voice_path=folder/str(source['stage18_voice_qa'])
        if voice_path.name!=str(source['stage18_voice_qa']) or not voice_path.is_file():
            errors.append('STAGE18_VOICE_QA_MISSING_OR_UNSAFE')
        else:
            try:
                voice=json.loads(voice_path.read_text(encoding='utf-8-sig'))
                if voice.get('word_forced_alignment_performed') is not False or voice.get('alignment')!='CHUNK_REAL_WAV_WORD_ESTIMATED':
                    errors.append('STAGE18_VOICE_QA_ALIGNMENT_CLAIM_INVALID')
                if abs(float(voice['voice_real_wav_seconds'])-float(source['duration_seconds']))>1.5:
                    errors.append('STAGE18_VOICE_DURATION_MISMATCH')
                for flag in voice.get('warnings',[]):warnings.append('STAGE18_REVIEW:'+str(flag))
            except (OSError,KeyError,ValueError,TypeError):
                errors.append('STAGE18_VOICE_QA_INVALID')
    if source.get('stage19_smart_crop_opt_in'):
        trace=folder/'smart_crop_report.json'
        if not trace.is_file():
            errors.append('STAGE19_MEDIA_QA_TRACE_MISSING')
        else:
            try:
                inspected=json.loads(trace.read_text(encoding='utf-8-sig'))
                if inspected.get('schema')!='STAGE19_CROP_REPORT_V1' or set(inspected.get('ratios',{}))!=set(declared):
                    errors.append('STAGE19_MEDIA_QA_TRACE_INVALID')
                for row in inspected['ratios'].values():
                    for shot in row:
                        focus=shot.get('focus') or {}
                        confidence=[focus.get('confidence')]+[f.get('confidence') for f in focus.get('track',[])]
                        if 'LOW' in confidence:
                            warnings.append('STAGE19_LOW_CONFIDENCE_CROP_NEEDS_VISUAL_REVIEW')
                        if int(focus.get('face_count',0) or 0)>1:
                            warnings.append('STAGE19_MULTI_FACE_CROP_NEEDS_VISUAL_REVIEW')
                        if shot.get('rights') and shot['rights'].get('human_commercial_rights_check_still_required') is not True:
                            errors.append('STAGE19_INVALID_RIGHTS_REVIEW_FLAG')
            except (ValueError,OSError,AttributeError,TypeError):
                errors.append('STAGE19_MEDIA_QA_TRACE_INVALID')
    rights=folder/"media_rights.json"
    if not rights.is_file():
        warnings.append("MEDIA_RIGHTS_LEDGER_MISSING")
        if source.get("demo") is not True:errors.append("MISSING_MEDIA_RIGHTS_LEDGER")
    else:
        try:
            rights_data=json.loads(rights.read_text(encoding="utf-8-sig"))
            if rights_data.get("rights_status")!="REVIEW_REQUIRED_BEFORE_PUBLICATION":
                warnings.append("MEDIA_RIGHTS_STATUS_UNKNOWN")
        except (OSError,ValueError):errors.append("MEDIA_RIGHTS_LEDGER_INVALID")
    if source.get("demo") is not True and source.get("remotion_frame_sampling_step",1)>1:
        errors.append("REAL_NEWS_CANNOT_USE_SAMPLED_FRAME_MODE")
    if source.get("demo") is True:
        warnings.append("DEMO_NOT_FOR_PUBLICATION")
        if source.get("remotion_frame_sampling_step",1)>1:
            warnings.append("DEMO_LOWER_NATIVE_MOTION_FPS_FRAME_DUPLICATION")
    if source.get("Piper_TTS") is not True:
        warnings.append("TTS_NOT_CONFIRMED")
    warnings.append("HUMAN_FACT_CHECK_MEDIA_RIGHTS_AND_FINAL_VIEWING_REQUIRED")
    report={"schema_version":1,"checked_at":dt.datetime.now(dt.timezone.utc).isoformat(),
            "folder":str(folder),"source_manifest":source.get("source_manifest"),
            "expected_aspect":expected_aspect,"demo":bool(source.get("demo")),
            "technical_pass":not errors,"status":"TECHNICAL_PASS_REVIEW_REQUIRED" if not errors else "FAIL",
            "errors":errors,"warnings":warnings,"formats":detail,
            "eligible_for_automatic_publication":False,
            "repairable_codes":["MISSING_SRT","INVALID_SRT"],
            "note":"Automated QA cannot establish factual correctness, copyright permission, or visual editorial quality."}
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--folder",required=True,type=Path)
    ap.add_argument("--report",required=True,type=Path)
    ap.add_argument("--expect",choices=["9:16","16:9","both"])
    ap.add_argument("--skip-frames",action="store_true")
    opt=ap.parse_args()
    if opt.report.exists():ap.error("report already exists: no overwrite")
    try:
        opt.report.parent.mkdir(parents=True,exist_ok=True)
        result=analyze(opt.folder,opt.report,opt.expect,not opt.skip_frames)
        with opt.report.open("x",encoding="utf-8") as f:
            json.dump(result,f,ensure_ascii=False,indent=2)
        print(json.dumps({"status":result["status"],"errors":result["errors"],
                          "warnings":result["warnings"],"report":str(opt.report)},ensure_ascii=False))
        if result["errors"]:sys.exit(2)
    except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired) as e:
        ap.exit(2,"QA_ERROR: "+str(e)+"\n")
if __name__=="__main__":main()
