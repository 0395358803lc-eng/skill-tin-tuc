#!/usr/bin/env python3
"""Measure CPU/RAM/VRAM and actual Stage-15 Remotion/Piper/FFmpeg job runtime.
Each benchmark run uses an exclusively NEW output folder. No auto-publishing.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

def stop_benchmark_process_tree(parent,app,psutil_module):
    """Only stop descendants of this benchmark job; leave other remote tasks untouched."""
    try:
        descendants=app.children(recursive=True)
    except (psutil_module.NoSuchProcess,psutil_module.AccessDenied):
        descendants=[]
    for child in reversed(descendants):
        try:child.terminate()
        except (psutil_module.NoSuchProcess,psutil_module.AccessDenied):pass
    try:parent.terminate()
    except (ProcessLookupError,PermissionError):pass
    gone,alive=psutil_module.wait_procs(descendants,timeout=5)
    for child in alive:
        try:child.kill()
        except (psutil_module.NoSuchProcess,psutil_module.AccessDenied):pass
    try:parent.wait(timeout=5)
    except subprocess.TimeoutExpired:parent.kill()

def pipeline_argv(input_file:Path,out:Path,encoder:str,sample_every:int,speech_rate:float)->list[str]:
    project=Path(__file__).resolve().parents[1]
    return [sys.executable,str(project/'scripts'/'video_pipeline.py'),
        '--input',str(input_file),'--out',str(out),'--allow-demo','--encoder',encoder,
        '--speech-rate',str(speech_rate),'--demo-sample-every',str(sample_every)]

def measure(input_file:Path,out:Path,encoder:str,report:Path,timeout:int=5400,sample_every:int=1,speech_rate:float=1.0,concurrency:int=1)->dict:
    import psutil
    if out.exists() or report.exists():
        raise ValueError('benchmark out/report path already exists; no overwrite')
    input_file=input_file.resolve()
    brief=json.loads(input_file.read_text(encoding='utf-8-sig'))
    if brief.get('demo') is not True:
        raise ValueError('benchmark refuses real news; only clearly marked DEMO allowed')
    if sample_every not in (1,2,3,5,6,10):raise ValueError('invalid frame sampling step')
    if not .75<=speech_rate<=1.35:raise ValueError('speech_rate out of range')
    if not 1<=concurrency<=4:raise ValueError('concurrency must be 1..4')
    project=Path(__file__).resolve().parents[1]
    runtime=Path(os.getenv('NEWS_SKILL_RUNTIME',project.parent/(project.name+'-runtime')))
    env=dict(os.environ,NEWS_SKILL_RUNTIME=str(runtime),PIPER_VOICE_DIR=str(runtime/'models'),
        PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',PIPER_BACKEND='inprocess',PIPER_SPEECH_RATE=str(speech_rate),
        REMOTION_CONCURRENCY=str(concurrency))
    env['PATH']=str(runtime/'tools'/'ffmpeg-selected')+os.pathsep+env.get('PATH','')
    argv=pipeline_argv(input_file,out,encoder,sample_every,speech_rate)
    report.parent.mkdir(parents=True,exist_ok=True)
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    t=time.perf_counter()
    with subprocess.Popen(argv,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,encoding='utf-8',errors='replace') as process:
        app=psutil.Process(process.pid)
        max_rss=0;max_cpu=0;max_gpu_memory=0;max_gpu_pct=0
        samples=[];expired=False;startup_stall=False
        while process.poll() is None:
            try:
                children=[app]+app.children(recursive=True)
                rss=sum(p.memory_info().rss for p in children if p.is_running())
                max_rss=max(max_rss,rss)
                cpu=sum(p.cpu_percent(interval=None) for p in children if p.is_running())
                max_cpu=max(max_cpu,cpu)
            except (psutil.NoSuchProcess,psutil.AccessDenied):
                rss=0;cpu=0
            vram,pct=None,None
            try:
                smi=subprocess.run(['nvidia-smi','--query-gpu=memory.used,utilization.gpu',
                    '--format=csv,noheader,nounits'],capture_output=True,text=True,
                    timeout=5)
                if smi.returncode==0:
                    vram,pct=[int(float(x.strip())) for x in smi.stdout.splitlines()[0].split(',')[:2]]
                    max_gpu_memory=max(max_gpu_memory,vram)
                    max_gpu_pct=max(max_gpu_pct,pct)
            except (FileNotFoundError,ValueError,IndexError,subprocess.TimeoutExpired):
                pass
            samples.append({'elapsed_s':round(time.perf_counter()-t,1),
                'process_tree_rss_mb':round(rss/1024**2,1),'gpu_used_mb':vram,
                'gpu_util_pct':pct,'cpu_percent_across_cores':round(cpu,1)})
            elapsed_check=time.perf_counter()-t
            if not out.exists() and elapsed_check>90:
                startup_stall=True
                stop_benchmark_process_tree(process,app,psutil)
                break
            if elapsed_check>timeout:
                expired=True
                stop_benchmark_process_tree(process,app,psutil)
                break
            time.sleep(2)
        log=process.stdout.read() if process.stdout else ''
        rc=process.returncode
    elapsed=round(time.perf_counter()-t,2)
    qa=None
    p=out/'qa_report.json'
    if p.is_file():
        try:qa=json.loads(p.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):pass
    metrics={'started_at':started,'elapsed_seconds':elapsed,'timeout':expired,
        'startup_stall_detected':startup_stall,
        'returncode':rc,'input':str(input_file),'output':str(out),
        'encoder_request':encoder,'speech_rate':speech_rate,'remotion_concurrency':concurrency,
        'speech_rate_forwarded_as_cli':True,
        'remotion_sample_every':sample_every,
        'native_motion_fps':round(30/sample_every,2),
        'peak_process_tree_rss_mb':round(max_rss/1024**2,1),
        'peak_gpu_used_mb':max_gpu_memory,'peak_gpu_util_pct':max_gpu_pct,
        'sample_count':len(samples),'samples':samples,
        'renderer_qa':{'status':qa.get('status'),'duration_seconds':qa.get('duration_seconds'),
           'formats':{k:v.get('qa',{}) for k,v in qa.get('formats',{}).items()}} if qa else None,
        'log_tail':log[-3500:],
        'limitations':'GPU used and utilization are whole-device readings, not exclusively this process; RSS is sampled process tree, CPU may miss child peaks.'}
    with report.open('x',encoding='utf-8') as f:
        json.dump(metrics,f,ensure_ascii=False,indent=2)
    (report.parent/(report.stem+'.log')).write_text(log,encoding='utf-8')
    return metrics

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--report',required=True,type=Path)
    ap.add_argument('--encoder',choices=['auto','cpu','nvenc'],default='auto')
    ap.add_argument('--demo-sample-every',type=int,default=1)
    ap.add_argument('--speech-rate',type=float,default=1.0)
    ap.add_argument('--remotion-concurrency',type=int,default=1)
    ap.add_argument('--timeout',type=int,default=5400)
    a=ap.parse_args()
    if a.timeout<60 or a.timeout>10800:ap.error('timeout must be 60..10800 seconds')
    try:
        data=measure(a.input,a.out,a.encoder,a.report,a.timeout,a.demo_sample_every,a.speech_rate,a.remotion_concurrency)
        print(json.dumps({k:v for k,v in data.items() if k not in ('samples','log_tail')},ensure_ascii=False,indent=2))
        if data['returncode']!=0:sys.exit(2)
    except (ValueError,OSError,RuntimeError) as e:
        ap.exit(2,'BENCHMARK_ERROR: '+str(e)+'\n')
if __name__=='__main__':main()
