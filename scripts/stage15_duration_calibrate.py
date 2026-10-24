#!/usr/bin/env python3
"""Stage 15: deterministic DEMO-only duration calibration with real local Piper.
No real editorial script is modified; artifacts go outside the Skill folder.
"""
from __future__ import annotations
import argparse,json,os,sys,hashlib,datetime as dt,time,wave
from pathlib import Path
import render_video as legacy
import video_pipeline as pipeline
from stage5_fixture import make, PATTERNS

def tokens(stories:list[dict])->int:
    return sum(len(x['narration'].split()) for x in stories)

def resize(brief:dict,desired:int)->dict:
    if brief.get('demo') is not True:raise ValueError('cannot resize real approved scripts')
    copy=json.loads(json.dumps(brief))
    count=len(copy['stories'])
    allocation=[desired//count+(1 if i<desired%count else 0) for i in range(count)]
    language=copy['language']
    for i,story in enumerate(copy['stories']):
        arr=[]
        j=i
        while len(arr)<allocation[i]:
            arr.extend(PATTERNS[language][j%len(PATTERNS[language])].split())
            j+=1
        story['narration']=' '.join(arr[:allocation[i]]).rstrip(' ,.?!')+'.'
    legacy.validate_brief(copy,allow_demo=True)
    return copy

def actual_audio(brief:dict,root:Path)->dict:
    if root.exists():raise ValueError('probe folder already exists')
    root.mkdir(parents=True)
    try:
        voice='vi_VN-vais1000-medium' if brief['language'].startswith('vi') else 'en_US-lessac-medium'
        start=time.perf_counter()
        narration,timings,cues,frames=pipeline.audio_track(brief,root,voice,False)
        with wave.open(str(narration),'rb') as f:
            measured=f.getnframes()/f.getframerate()
        return {'seconds':round(measured,3),'video_seconds':round(frames/pipeline.FPS,3),
            'tokens':tokens(brief['stories']),'story_count':len(timings),
            'caption_cues':len(cues),'tts_elapsed_s':round(time.perf_counter()-start,2)}
    finally:
        pass

def calibrate(seconds:int,language:str,root:Path,tolerance:float=.05,max_attempts:int=3)->dict:
    if language not in PATTERNS or seconds not in (30,60,90,180):
        raise ValueError('invalid stage-15 profile')
    if root.exists():raise ValueError('output exists, no overwrite')
    root.mkdir(parents=True)
    baseline=make(seconds,language,'both')
    current=tokens(baseline['stories'])
    trials=[]
    best=None
    for attempt in range(1,max_attempts+1):
        brief=resize(baseline,current)
        attempt_dir=root/f'probe-{attempt:02d}'
        reading=actual_audio(brief,attempt_dir)
        drift=round(reading['seconds']-seconds,3)
        rec={'attempt':attempt,'requested_tokens':current,'duration_error_s':drift,
            'error_pct':round(100*drift/seconds,2),**reading}
        trials.append(rec)
        if best is None or abs(drift)<abs(best[1]):
            best=(brief,drift,reading,attempt)
        if abs(drift)<=seconds*tolerance:
            break
        current=max(40,min(900,round(current*seconds/max(1,reading['seconds']))))
        if current==rec['requested_tokens']:
            current+=1 if drift<0 else -1
    chosen,err,reading,n=best
    manifest=root/'calibrated_demo.json'
    with manifest.open('x',encoding='utf-8') as f:json.dump(chosen,f,ensure_ascii=False,indent=2)
    report={'target_seconds':seconds,'language':language,'source':'synthetic_only',
        'best_attempt':n,'measured_duration':reading['seconds'],
        'target_error_seconds':err,'target_error_pct':round(100*err/seconds,2),
        'within_five_percent':abs(err)<=seconds*tolerance,
        'native_fps_rendered':False,'trials':trials,'manifest':str(manifest),
        'note':'Piper audio-only calibration; NOT full video QA or approved real editorial media.'}
    (root/'calibration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--root',required=True,type=Path)
    ap.add_argument('--profile',action='append',choices=['30:en-US','60:vi-VN','90:en-US','180:en-US',
        '30:vi-VN','60:en-US','90:vi-VN','180:vi-VN'])
    ap.add_argument('--max-attempts',type=int,default=3)
    a=ap.parse_args()
    if not 1<=a.max_attempts<=4:ap.error('max-attempts must be 1..4')
    if a.root.exists():ap.error('root exists; no overwrite')
    a.root.mkdir(parents=True)
    skill=Path(__file__).resolve().parents[1]
    runtime=Path(os.environ.get('NEWS_SKILL_RUNTIME',
        str(skill.parent/(skill.name+'-runtime'))))
    os.environ['PIPER_VOICE_DIR']=str(runtime/'models')
    os.environ['PIPER_BACKEND']='inprocess'
    os.environ['PIPER_SPEECH_RATE']='1.0'
    results=[]
    for profile in a.profile or ['30:en-US','60:vi-VN','90:en-US','180:en-US']:
        sec,lang=profile.split(':')
        r=calibrate(int(sec),lang,a.root/('target-'+sec+'-'+lang),max_attempts=a.max_attempts)
        results.append(r)
        print(json.dumps({k:r[k] for k in ('target_seconds','language','measured_duration',
          'target_error_pct','within_five_percent','best_attempt')},ensure_ascii=False),flush=True)
    (a.root/'summary.json').write_text(json.dumps({'results':results,'timestamp':dt.datetime.now(dt.timezone.utc).isoformat()},
        ensure_ascii=False,indent=2),encoding='utf-8')
    if not all(x['within_five_percent'] for x in results):sys.exit(3)
if __name__=='__main__':main()
