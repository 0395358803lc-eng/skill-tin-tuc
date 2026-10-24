#!/usr/bin/env python3
"""Non-destructive Stage-15 reliability checks on native-30fps videos.
Creates independent QA reports/corruption fixtures only in a NEW runtime folder.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,shutil,sys,os
from pathlib import Path
import qa_engine as qa

def getjson(p:Path)->dict:return json.loads(p.read_text(encoding='utf-8-sig'))
def snapshot(inputs:list[Path])->dict:
    return {str(p):qa.digest(p) for p in inputs}
def export(report_path:Path,data:dict):
    with report_path.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
def stage15_native_profiles(base:Path,delivery:Path)->list[tuple[int,Path]]:
    return [(30,base/'demo30-both-render'),(60,base/'demo60-both-render'),
      (90,base/'demo90-native30-rate085'),(180,base/'demo180-native30-concurrency3'),
      (60,delivery)]
def check_profiles(base:Path,delivery:Path,root:Path)->list:
    metrics=[]
    profiles=stage15_native_profiles(base,delivery)
    immutable=[]
    for _,folder in profiles:
        source=getjson(folder/'qa_report.json')
        immutable += [folder/item['file'] for item in source['formats'].values()]
        immutable += [folder/'subtitles_9x16.srt',folder/'subtitles_16x9.srt',
            folder/'qa_report.json']
    baseline=snapshot(immutable)
    for idx,(target,folder) in enumerate(profiles):
        source=getjson(folder/'qa_report.json')
        if source.get('remotion_frame_sampling_step',1)!=1 or source.get('motion_quality','NATIVE_30FPS')!='NATIVE_30FPS':
            raise ValueError(f'not native 30 fps: {folder}')
        report=qa.analyze(folder,root/f'qa-pass-{idx+1}.json','both',frames=False)
        export(root/f'qa-pass-{idx+1}.json',report)
        fmt=report['formats']
        valid=bool(report['technical_pass'] and not report['errors'] and set(fmt)=={'9:16','16:9'})
        if not valid:raise RuntimeError('QA native FAIL:'+folder.as_posix()+repr(report['errors']))
        if any(a['fps']!=30 for a in fmt.values()):
            raise RuntimeError('wrong FPS')
        dur=sum(x['duration_seconds'] for x in fmt.values())/2
        for _ in range(2) if idx==4 else range(0):
            copy=qa.analyze(folder,root/f'qa-repeat-{_+1}.json','both',frames=False)
            export(root/f'qa-repeat-{_+1}.json',copy)
            if copy['errors'] or {k:v['sha256'] for k,v in fmt.items()} != {
                 k:v['sha256'] for k,v in copy['formats'].items()}:
                raise RuntimeError('repeated QA unstable')
        metrics.append({'target_s':target,'actual_s':round(dur,3),
            'duration_error_pct':round(100*(dur-target)/target,2),
            'within_five_percent':abs(dur-target)<=target*.05,
            'native_30_fps':True,'technical_qa_pass':valid,
            'folder':str(folder),'qa_warnings':report['warnings'],
            'mp4_hashes':{k:v['sha256'] for k,v in fmt.items()}})
    if snapshot(immutable)!=baseline:
        raise RuntimeError('source videos changed during QA')
    return metrics

def negative_checks(base:Path,root:Path)->dict:
    original=base/'demo30-both-render'
    errors={}
    for case in ('bad_srt','corrupt_video','deleted_video'):
        output=root/case
        output.mkdir()
        for fname in ('qa_report.json','sources.json','publishing_metadata.json',
          'media_rights.json','narration.wav','subtitles_9x16.srt','subtitles_16x9.srt',
          'DEMO_DO_NOT_PUBLISH_9x16.mp4','DEMO_DO_NOT_PUBLISH_16x9.mp4'):
            src=original/fname
            if not src.exists():raise RuntimeError('missing fixture:'+str(src))
            shutil.copy2(src,output/fname)
        if case=='bad_srt':
            (output/'subtitles_9x16.srt').write_text('INVALID SRT',encoding='utf-8')
            expected='INVALID_SRT:9:16'
        elif case=='corrupt_video':
            (output/'DEMO_DO_NOT_PUBLISH_9x16.mp4').write_bytes(b'garbled')
            expected='MISSING_VIDEO:9:16'
        else:
            (output/'DEMO_DO_NOT_PUBLISH_16x9.mp4').unlink()
            expected='MISSING_VIDEO:16:9'
        data=qa.analyze(output,root/f'{case}-result.json','both',frames=False)
        export(root/f'{case}-result.json',data)
        if data['technical_pass'] or not any(x.startswith(expected) for x in data['errors']):
            raise RuntimeError('negative QA failed to reject '+case+':'+repr(data['errors']))
        errors[case]=data['errors']
    return errors

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True,type=Path)
    skill=Path(__file__).resolve().parents[1]
    runtime=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(skill.parent/(skill.name+'-runtime'))))
    parser.add_argument('--bench',type=Path,default=runtime/'stage5-bench')
    parser.add_argument('--delivery',type=Path,default=runtime/'deliveries'/'Tin-Cong-Nghe-My-20261024-60s')
    a=parser.parse_args()
    if a.root.exists():parser.error('root exists, no overwrite')
    a.root.mkdir(parents=True)
    base=a.bench.resolve()
    delivery=a.delivery.resolve()
    cases=check_profiles(base,delivery,a.root)
    neg=negative_checks(base,a.root)
    result={'status':'STABILITY_QA_PASS','checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
        'native_profiles':cases,'repeated_qa_delivery_count':3,
        'negative_tests':neg,'source_mp4_unchanged':True,
        'limitations':'QA cannot certify visual caption overlap or content accuracy; durations below target are warnings, not QA-fatal.'}
    export(a.root/'stage15_stability.json',result)
    print(json.dumps({'status':result['status'],'profiles':[
        {'target':x['target_s'],'real_duration':x['actual_s'],'duration_delta_pct':x['duration_error_pct'],
         'native':x['native_30_fps'],'qa_pass':x['technical_qa_pass']} for x in cases],
         'negative_tests':list(neg),'repeated_qa_delivery_count':3},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
