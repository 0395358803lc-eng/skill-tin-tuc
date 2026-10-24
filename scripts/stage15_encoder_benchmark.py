#!/usr/bin/env python3
"""Short repeatable FFmpeg encoding benchmark; GPU comparison not apples-to-apples quality."""
import argparse,datetime as dt,json,statistics,subprocess,time,os
from pathlib import Path
def run_once(ffmpeg:Path,ffprobe:Path,source:Path,out:Path,codec:str)->dict:
    if out.exists():raise ValueError('output exists')
    cmd=[str(ffmpeg),'-hide_banner','-nostats','-loglevel','error','-i',str(source),
         '-frames:v','120','-an','-c:v',codec]
    if codec=='libx264':cmd+=['-preset','veryfast','-crf','21']
    else:cmd+=['-preset','p4','-cq','22','-b:v','7M']
    cmd+=['-pix_fmt','yuv420p','-movflags','+faststart','-y',str(out)]
    start=time.perf_counter()
    process=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    elapsed=round(time.perf_counter()-start,3)
    result={'codec':codec,'elapsed_s':elapsed,'success':process.returncode==0,
        'stderr_tail':process.stderr[-300:],'file_size_bytes':out.stat().st_size if out.exists() else 0}
    if process.returncode==0:
        probe=subprocess.run([str(ffprobe),'-v','error','-show_entries','stream=codec_name,avg_frame_rate,width,height:format=duration',
          '-of','json',str(out)],capture_output=True,text=True,timeout=25,check=True)
        info=json.loads(probe.stdout)
        result['probe']={'duration':float(info['format']['duration']),'fps':info['streams'][0]['avg_frame_rate'],
            'width':info['streams'][0]['width'],'height':info['streams'][0]['height']}
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--repetitions',type=int,default=3)
    skill=Path(__file__).resolve().parents[1]
    runtime=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(skill.parent/(skill.name+'-runtime'))))
    p.add_argument('--tools',type=Path,default=runtime/'tools'/'ffmpeg-selected')
    a=p.parse_args()
    if a.out.exists():p.error('output already exists')
    if not a.source.is_file():p.error('source missing')
    if a.repetitions not in (1,2,3,4):p.error('repetitions must be 1..4')
    a.out.mkdir(parents=True)
    results=[]
    for rep in range(a.repetitions):
        for name in ('libx264','h264_nvenc'):
            result=run_once(a.tools/'ffmpeg.exe',a.tools/'ffprobe.exe',a.source,a.out/f'{rep+1:02d}-{name}.mp4',name)
            result['repetition']=rep+1
            results.append(result)
            print(json.dumps({k:v for k,v in result.items() if k!='probe'},ensure_ascii=False),flush=True)
    grouped={}
    for codec in ('libx264','h264_nvenc'):
        passed=[x for x in results if x['codec']==codec and x['success']]
        grouped[codec]={'successful_repeats':len(passed),'mean_elapsed_s':round(statistics.mean(x['elapsed_s'] for x in passed),3) if passed else None,
                        'max_elapsed_s':max((x['elapsed_s'] for x in passed),default=None)}
    report={'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source':str(a.source),
        'repetitions':a.repetitions,'results':results,'aggregate':grouped,
        'cautions':'4 seconds of source (120 frames), comparisons use different presets and quality settings; short runs/other load cannot establish end-to-end or visual-quality superiority.'}
    (a.out/'encoder_benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(not r['success'] for r in results):raise RuntimeError('one or more encoder repetitions failed')
if __name__=='__main__':main()
