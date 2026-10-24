#!/usr/bin/env python3
"""Exact Piper audio preflight before editorial draft freeze and user's approval.
Does not modify the script, user approval, or produce distributable news video.
"""
from __future__ import annotations
import argparse,hashlib,json,os,sys,time,wave
from pathlib import Path
import video_pipeline as pipe
import render_video as legacy

def preflight(brief_file:Path,out:Path,speech_rate:float=1.0,voice:str|None=None)->dict:
    if out.exists():raise ValueError('preflight output already exists')
    if not .75<=speech_rate<=1.35:raise ValueError('invalid speech rate')
    obj=json.loads(brief_file.read_text(encoding='utf-8-sig'))
    if brief_file.name.lower()=='approved.json' or obj.get('status')=='approved' and not obj.get('demo'):
        raise ValueError('use preflight on editorial candidate BEFORE approval, never change approved content')
    lang=obj.get('language')
    if lang not in ('vi-VN','en-US','en-GB'):raise ValueError('invalid language')
    target=obj.get('target_seconds')
    valid_targets=(15,30,60,90,180) if obj.get('demo') is True else (30,60,90,180)
    if type(target)!=int or target not in valid_targets:raise ValueError('unsupported target')
    stories=obj.get('stories')
    if not isinstance(stories,list) or not 1<=len(stories)<=8:
        raise ValueError('invalid story count')
    texts=[x.get('narration') for x in stories]
    if any(not isinstance(t,str) or not 10<=len(t)<=4000 for t in texts):
        raise ValueError('empty or oversized narration')
    voices={'vi-VN':'vi_VN-vais1000-medium','en-US':'en_US-lessac-medium','en-GB':'en_US-lessac-medium'}
    selected=voice or voices[lang]
    if not selected.startswith('vi_' if lang=='vi-VN' else 'en_'):raise ValueError('voice language mismatch')
    skill=Path(__file__).resolve().parents[1]
    runtime=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(skill.parent/(skill.name+'-runtime'))))
    model_dir=Path(os.environ.get('PIPER_VOICE_DIR',str(runtime/'models')))
    if not (model_dir/(selected+'.onnx')).is_file() or not (model_dir/(selected+'.onnx.json')).is_file():
        raise ValueError('local Piper voice model/config unavailable: '+selected)
    out.mkdir(parents=True)
    os.environ['PIPER_VOICE_DIR']=str(model_dir)
    os.environ['PIPER_BACKEND']='inprocess'
    os.environ['PIPER_SPEECH_RATE']=str(speech_rate)
    start=time.perf_counter()
    wav,timings,cues,frames=pipe.audio_track(obj,out,selected,False)
    with wave.open(str(wav),'rb') as f:seconds=f.getnframes()/f.getframerate()
    total_words=sum(len(t.split()) for t in texts)
    error_pct=100*(seconds-target)/target
    result={'input_file':str(brief_file),'input_sha256':hashlib.sha256(brief_file.read_bytes()).hexdigest(),
        'target_seconds':target,'measured_seconds':round(seconds,3),'video_frames_estimate':frames,
        'error_pct':round(error_pct,2),'within_five_percent':abs(error_pct)<=5,
        'caption_cues':len(cues),'story_count':len(stories),'whitespace_tokens':total_words,
        'suggested_token_adjustment':round(total_words*(target/max(.1,seconds)-1)),
        'voice':selected,'speech_rate':speech_rate,'elapsed_s':round(time.perf_counter()-start,2),
        'audio_preview':str(wav),
        'next':'If duration outside tolerance, revise the UNAPPROVED candidate and run preflight in another NEW folder before freezing a draft. After script approval, no automatic alterations are allowed.'}
    (out/'duration_preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--speech-rate',type=float,default=1.0)
    p.add_argument('--voice')
    o=p.parse_args()
    try:
        result=preflight(o.input,o.out,o.speech_rate,o.voice)
        print(json.dumps({k:v for k,v in result.items() if k not in ('input_file','audio_preview')},ensure_ascii=False))
        if not result['within_five_percent']:sys.exit(3)
    except (ValueError,OSError,RuntimeError,KeyError) as exc:p.exit(2,'PREFLIGHT_ERROR: '+str(exc)+'\n')
if __name__=='__main__':main()
