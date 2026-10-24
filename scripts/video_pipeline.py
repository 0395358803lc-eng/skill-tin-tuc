#!/usr/bin/env python3
"""News video v0.4 renderer: source-checked media, Piper, subtitles, Remotion, FFmpeg."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import render_video as legacy
import editorial_core as editorial
import qa_engine
import narration_quality
import smart_media
import studio_design
import runtime_tools

FPS = 30
FORMATS = {'9:16': ('NewsVertical', 1080, 1920, '9x16'),
           '16:9': ('NewsHorizontal', 1920, 1080, '16x9')}
VALID_MEDIA = {'licensed_image', 'licensed_broll', 'news_card', 'infographic'}
def execute(argv: list[str], cwd: Path | None = None, timeout: int = 1200) -> str:
    p = subprocess.run([str(a) for a in argv], cwd=str(cwd) if cwd else None,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, encoding='utf-8', errors='replace', timeout=timeout)
    if p.returncode:
        raise RuntimeError('command failed ('+str(p.returncode)+'): '+' '.join(map(str, argv))+'\n'+p.stdout[-3500:])
    return p.stdout

def secure_path(base: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('media path must be safe relative path within approved manifest folder')
    resolved = (base / relative).resolve()
    if not resolved.is_relative_to(base.resolve()) or not resolved.is_file():
        raise ValueError('media path missing, unsafe or outside manifest folder: '+relative)
    return resolved

def approved_audio_asset(brief:dict, manifest_folder:Path, prefix:str,
                         requested:Path|None=None)->Path|None:
    """Reject unapproved replacements of script-locked local audio."""
    name, expected=brief.get(prefix+'_path'),brief.get(prefix+'_sha256')
    if name is None and expected is None:
        if requested is not None:
            raise ValueError(prefix+' override is not approved')
        if prefix=='music' and brief.get('music_license'):
            raise ValueError('music license without approved media')
        return None
    if not isinstance(name,str) or not name or not isinstance(expected,str) or len(expected)!=64:
        raise ValueError(prefix+' approved path/SHA-256 incomplete')
    if any(x not in '0123456789abcdefABCDEF' for x in expected):
        raise ValueError(prefix+' approved SHA-256 invalid')
    resolved=secure_path(manifest_folder,name)
    if requested is not None and requested.resolve()!=resolved:
        raise ValueError(prefix+' CLI path differs from approved media')
    if qa_engine.digest(resolved).lower()!=expected.lower():
        raise ValueError(prefix+' checksum differs from approved script')
    if prefix=='music':
        if not isinstance(brief.get('music_license'),str) or not brief['music_license'].strip():
            raise ValueError('background music needs approved license evidence')
        if resolved.suffix.lower() not in ('.wav','.mp3','.flac','.m4a','.ogg'):
            raise ValueError('unsupported music file type')
    elif resolved.suffix.lower()!='.json':
        raise ValueError('pronunciation lexicon must be JSON')
    return resolved

def choose_media(item: dict) -> dict | None:
    visual_plan = item.get('visual_plan') or []
    for scene in visual_plan:
        if not isinstance(scene, dict):
            raise ValueError('visual plan entry must be an object')
        kind = scene.get('type')
        if kind not in VALID_MEDIA:
            raise ValueError('unsupported visual_plan type: '+str(kind))
        if kind == 'infographic':
            points=scene.get('data_points',[])
            if not isinstance(points,list) or not 1<=len(points)<=5 or any(not isinstance(pt,dict) or not isinstance(pt.get('label'),str) or type(pt.get('value')) not in (float,int) or not 0<=pt['value']<=100 for pt in points):
                raise ValueError('infographic requires 1..5 numeric data_points (label, value 0..100)')
            return {'kind':'infographic','data_points':points,'title':str(scene.get('title','SỐ LIỆU MINH HỌA'))[:80]}
        if kind in ('licensed_image','licensed_broll'):
            if not isinstance(scene.get('license_evidence'), str) or not scene['license_evidence'].strip():
                raise ValueError('media must have rights evidence')
            if not scene.get('media_path'):
                raise ValueError('licensed scene missing media_path')
            return {'kind': 'image' if kind=='licensed_image' else 'video',
                    'media_path': scene['media_path'], 'media_sha256':scene.get('media_sha256'),
                    'focal_x': float(scene.get('focal_x', .5)),
                    'focal_y': float(scene.get('focal_y', .5)),
                    'manual_focus':('focal_x' in scene or 'focal_y' in scene),
                    'smart_crop':scene.get('smart_crop') is True,
                    'rights':{key:scene.get(key) for key in
                        ('source_url','author','license_name','attribution','license_evidence','media_sha256')}}
    if item.get('image_path'):
        if not item.get('image_license'):
            raise ValueError('image license missing')
        return {'kind':'image','media_path':item['image_path'],'focal_x':.5,'focal_y':.5}
    return None

def fit_image(src: Path, dst: Path, width: int, height: int, focal_x: float, focal_y: float) -> None:
    from PIL import Image, ImageOps
    if not (0 <= focal_x <= 1 and 0 <= focal_y <= 1):
        raise ValueError('focal point must be normalized 0..1')
    with Image.open(src) as src_image:
        image = ImageOps.exif_transpose(src_image).convert('RGB')
        # Cover: never stretch. Center on user-supplied focal point when available.
        scale = max(width/image.width, height/image.height)
        rw, rh = max(width,round(image.width*scale)),max(height,round(image.height*scale))
        image = image.resize((rw,rh),Image.Resampling.LANCZOS)
        ox = min(max(0,round(focal_x*rw-width/2)),rw-width)
        oy = min(max(0,round(focal_y*rh-height/2)),rh-height)
        image.crop((ox,oy,ox+width,oy+height)).save(dst,'JPEG',quality=89,optimize=True)

def prepare_media(item: dict, base: Path, public_assets: Path,
                  index: int, width: int, height: int, seconds: float, jobkey: str = 'default') -> dict | None:
    chosen = choose_media(item)
    if chosen is None:
        return None
    if chosen['kind']=='infographic':
        return chosen
    src = secure_path(base, chosen['media_path'])
    if chosen.get('media_sha256') and qa_engine.digest(src).lower()!=chosen['media_sha256'].lower():
        raise ValueError('licensed media file differs from approved SHA-256 fingerprint')
    fx,fy = chosen['focal_x'],chosen['focal_y']
    if not 0<=fx<=1 or not 0<=fy<=1:
        raise ValueError('focal coordinates must be within 0..1')
    focus={'focal_x':fx,'focal_y':fy,'method':'APPROVED_MANUAL_OR_CENTER'}
    if chosen.get('smart_crop') and not chosen.get('manual_focus'):
        if not chosen.get('media_sha256'):
            raise ValueError('Smart Crop requires SHA-256 of approved media')
        if chosen['kind']=='image':
            focus=smart_media.image_focus(src)
        else:
            focus=smart_media.video_focus(src,seconds,samples=7)
        fx=focus.get('focal_x',focus.get('mean_focus',{}).get('focal_x',.5))
        fy=focus.get('focal_y',focus.get('mean_focus',{}).get('focal_y',.5))
    stem = f'asset-{jobkey}-{index:03d}-{width}x{height}'
    if chosen['kind']=='image':
        name = stem+'.jpg'
        fit_image(src,public_assets/name,width,height,fx,fy)
    else:
        name = stem+'.mp4'
        filt = smart_media.crop_filter(width,height,focus)
        execute(['ffmpeg','-y','-hide_banner','-loglevel','error',
                 '-stream_loop','-1','-i',src,'-t',f'{seconds:.4f}',
                 '-vf',filt,'-an','-c:v','libx264','-preset','veryfast','-crf','24',
                 '-movflags','+faststart',public_assets/name],timeout=600)
    return {'kind':chosen['kind'],'asset':name,
        'focus_trace':focus,
        'rights_trace':smart_media.rights_record(
            {'media_path':chosen['media_path'],**chosen.get('rights',{})},
            src,qa_engine.digest(src)) if chosen.get('smart_crop') else None}

def audio_track(brief: dict, out: Path, voice: str, demo_silence: bool):
    work=out/'_work'
    work.mkdir(exist_ok=False)
    voice_files=[]
    story_timings=[]
    all_cues=[]
    start_frames=0
    src_fmt=None
    for i,item in enumerate(brief['stories'],1):
        parts=legacy.chunks(item['narration'],max_chars=58)
        wav,sub,duration=legacy.build_audio(parts,work,f'story_{i:02d}',voice,demo_silence)
        with wave.open(str(wav),'rb') as w:
            fmt=(w.getframerate(),w.getnchannels(),w.getsampwidth())
        if src_fmt and fmt != src_fmt:
            raise RuntimeError('Different audio WAV formats across stories')
        src_fmt=fmt
        nframes=max(FPS,int(math.ceil(duration*FPS)))
        start=start_frames/FPS
        all_cues.extend({'start':round(start+s,3),'end':round(start+e,3),'text':t} for s,e,t in sub)
        story_timings.append({'durationFrames':nframes,'startFrames':start_frames,
                              'voice':str(wav),'duration_seconds':nframes/FPS})
        voice_files.append(wav)
        start_frames += nframes
    narration=out/'narration.wav'
    with wave.open(str(narration),'wb') as merged:
        merged.setframerate(src_fmt[0]); merged.setnchannels(src_fmt[1]); merged.setsampwidth(src_fmt[2])
        for path,timing in zip(voice_files,story_timings):
            with wave.open(str(path),'rb') as src:
                data=src.readframes(src.getnframes())
                merged.writeframes(data)
                actual_samples=src.getnframes()
            expected_samples=round(timing['durationFrames']/FPS*src_fmt[0])
            if expected_samples>actual_samples:
                merged.writeframes(b'\0'*(expected_samples-actual_samples)*src_fmt[1]*src_fmt[2])
    return narration,story_timings,all_cues,start_frames

def select_encoder(preference: str) -> str:
    if preference=='cpu':
        return 'libx264'
    supported=legacy.nvenc_available()
    if preference=='nvenc' and not supported:
        raise RuntimeError('GPU requested but operational NVENC encode probe failed')
    return 'h264_nvenc' if supported else 'libx264'

def ffmpeg_master(video: Path, narration: Path, output: Path, encoder: str,
                  music: Path | None = None, repeat_to_30fps: bool = False) -> None:
    args=['ffmpeg','-y','-hide_banner','-loglevel','error','-i',video,'-i',narration]
    if music:
        args+=['-stream_loop','-1','-i',music,
               '-filter_complex','[1:a]volume=1.0,asplit=2[n][side];[2:a]volume=0.20[m];[m][side]sidechaincompress=threshold=0.06:ratio=6:attack=40:release=400[duck];[n][duck]amix=inputs=2:duration=first:weights=1 0.30,loudnorm=I=-16:TP=-1.5:LRA=11[a]',
               '-map','0:v:0','-map','[a]']
    else:
        args+=['-map','0:v:0','-map','1:a:0','-af','loudnorm=I=-16:TP=-1.5:LRA=11']
    if repeat_to_30fps:
        args+=['-vf','fps=30']  # DEMO stress only: duplicate frames, not native 30-fps motion.
    if encoder=='h264_nvenc':
        args+=['-c:v','h264_nvenc','-preset','p4','-cq','22','-b:v','7M']
    else:
        args+=['-c:v','libx264','-preset','veryfast','-crf','21']
    args+=['-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-ar','48000',
           '-movflags','+faststart','-shortest',output]
    execute(args,timeout=1500)

def quality_check(path:Path, width:int,height:int,duration_frames:int) -> dict:
    raw=json.loads(execute(['ffprobe','-v','error','-show_streams','-show_format','-of','json',path]))
    v=next((x for x in raw['streams'] if x['codec_type']=='video'),None)
    a=next((x for x in raw['streams'] if x['codec_type']=='audio'),None)
    if not v or not a or (v.get('width'),v.get('height'))!=(width,height) or v.get('codec_name')!='h264' or a.get('codec_name')!='aac':
        raise RuntimeError('QA stream/format mismatch')
    seconds=float(raw['format']['duration'])
    if abs(seconds-duration_frames/FPS) > 1.0:
        raise RuntimeError('QA duration mismatch: '+str(seconds))
    return {'resolution':f'{width}x{height}','seconds':round(seconds,2),
            'video_codec':v['codec_name'],'audio_codec':a['codec_name'],
            'fps':v.get('avg_frame_rate'), 'audio_rate':a.get('sample_rate')}

def render(brief:dict, brief_file:Path, root:Path, aspect:str, voice:str,
           encoder_choice:str, silence:bool=False,music:Path|None=None,
           allow_longer:bool=False, sample_every:int=1) -> dict:
    if sample_every>1 and brief.get('demo') is not True:
        raise ValueError('frame sampling is forbidden for real approved news videos')
    music=approved_audio_asset(brief,brief_file.parent,'music',music)
    chosen_lexicon=os.environ.get('PIPER_PRONUNCIATION_MAP')
    approved_lexicon=approved_audio_asset(brief,brief_file.parent,'pronunciation_lexicon',
                         Path(chosen_lexicon) if chosen_lexicon else None)
    if approved_lexicon:
        os.environ['PIPER_PRONUNCIATION_MAP']=str(approved_lexicon)
    else:
        os.environ.pop('PIPER_PRONUNCIATION_MAP',None)
    design=studio_design.validate(brief)  # Must come from the approved manifest; never CLI override.
    runtime=Path(os.getenv('NEWS_SKILL_RUNTIME',str(Path(__file__).resolve().parents[2] / (Path(__file__).resolve().parents[1].name+'-runtime')))).resolve()
    remotion=runtime/'remotion'
    if not (remotion/'node_modules'/'remotion').exists() or not (remotion/'src'/'News.jsx').exists():
        raise RuntimeError('Remotion runtime not installed. Run scripts/setup_remotion.ps1 first.')
    encoder=select_encoder(encoder_choice)
    concurrency=int(os.environ.get('REMOTION_CONCURRENCY','1'))
    if not 1<=concurrency<=4:
        raise ValueError('REMOTION_CONCURRENCY must be 1..4')
    root.mkdir(parents=True,exist_ok=False)
    studio_design.save_preflight(brief,root/'visual_design.json')
    narration,timings,cues,frames=audio_track(brief,root,voice,silence)
    try:
        pronunciation=(json.loads(Path(os.environ['PIPER_PRONUNCIATION_MAP']).read_text(encoding='utf-8-sig'))
             if os.environ.get('PIPER_PRONUNCIATION_MAP') else {})
    except (OSError,ValueError) as exc:
        raise ValueError('invalid approved pronunciation map') from exc
    voice_qa=narration_quality.save_audit(cues,narration,brief,root/'voice_qa.json',pronunciation)
    emphasized=narration_quality.enrich_cues(cues)
    if music and not brief.get('music_license'):
        raise ValueError('background music requires explicit music_license evidence')
    output={}
    media_crop_reports={}
    for ratio in (['9:16','16:9'] if aspect=='both' else [aspect]):
        name,w,h,suffix=FORMATS[ratio]
        assets=remotion/'public'/'assets'
        assets.mkdir(parents=True,exist_ok=True)
        scenes=[]
        media_crop_reports[ratio]=[]
        jobkey=hashlib.sha256(str(root).encode('utf-8')).hexdigest()[:12]
        for i,(story,timing) in enumerate(zip(brief['stories'],timings),1):
            plan=story.get('visual_plan') or [{'type':'news_card','instruction':'original news graphics'}]
            if not isinstance(plan,list) or not plan or len(plan)>editorial.MAX_VISUAL_SCENES:
                raise ValueError(f'visual_plan must contain 1..{editorial.MAX_VISUAL_SCENES} scenes')
            shots=[]
            for j,scene in enumerate(plan,1):
                if not isinstance(scene,dict):
                    raise ValueError('visual_plan scene must be JSON object')
                entry=dict(story,visual_plan=[scene],image_path=None)
                media=prepare_media(entry,brief_file.parent,assets,i*100+j,w,h,timing['duration_seconds'],jobkey)
                if media and media.get('kind') in ('image','video'):
                    media_crop_reports[ratio].append({
                        'story_index':i,'shot_index':j,'ratio':ratio,
                        'source_type':scene.get('type'),
                        'source_path':scene.get('media_path',''),
                        'source_sha256':scene.get('media_sha256'),
                        'focus':media.get('focus_trace'),
                        'rights':media.get('rights_trace'),
                        'human_scene_relevance_review_required':True})
                shots.append({'media':media})
            if not any(s['media'] is not None for s in shots) and story.get('image_path'):
                media=prepare_media(dict(story,visual_plan=[]),brief_file.parent,assets,i,w,h,timing['duration_seconds'],jobkey)
                shots=[{'media':media}]
            scenes.append({'headline':story['headline'],'summary':story['summary'],
                           'source':' • '.join(x.get('title','') for x in story['sources'][:2]),
                           'durationFrames':timing['durationFrames'],
                           'shots':shots,'media':shots[0]['media']})
        props={'stories':scenes,'cues':emphasized,'durationFrames':frames,'category':brief['category'],
               'country':brief['country'],'demo':brief.get('demo') is True,
               'visualStyle':design['visual_style'],'language':brief['language'],
               'introFrames':design['intro_frames'],'outroFrames':design['outro_frames'],
               'transitionFrames':design['transition_frames']}
        props_file=root/('_work/props-'+suffix+'.json')
        props_file.write_text(json.dumps(props,ensure_ascii=False,indent=2),encoding='utf-8')
        raw=root/('_work/remotion-'+suffix+'.mp4')
        exe=remotion/'node_modules'/'.bin'/'remotion.cmd'
        browser=runtime_tools.find_browser()
        if browser is None:
            raise RuntimeError('Chrome/Chromium not found. Install a supported browser or set NEWS_CHROME_PATH.')
        command=[exe,'render','src/index.jsx',name,raw,'--props',props_file,
                 '--duration',str(frames),'--codec','h264','--x264-preset','veryfast','--crf','18','--concurrency',str(concurrency),
                 '--log','error','--hardware-acceleration','disable']
        if sample_every>1:
            command+=['--every-nth-frame',str(sample_every)]
        command+=['--browser-executable',str(browser)]
        log=execute(command,cwd=remotion,timeout=2400)
        (root/('_work/remotion-'+suffix+'.log')).write_text(log[-8000:],encoding='utf-8')
        final=root/('DEMO_DO_NOT_PUBLISH_'+suffix+'.mp4' if brief.get('demo') else 'news_video_'+suffix+'.mp4')
        ffmpeg_master(raw,narration,final,encoder,music,repeat_to_30fps=sample_every>1)
        qa=quality_check(final,w,h,frames)
        qa['encoder']=encoder
        qa['remotion_composition']=name
        qa['technical_pass']=True
        output[ratio]={'file':final.name,'qa':qa}
        legacy.write_srt([(x['start'],x['end'],x['text']) for x in cues],root/('subtitles_'+suffix+'.srt'))
    (root/'smart_crop_report.json').write_text(
        json.dumps({'schema':'STAGE19_CROP_REPORT_V1','ratios':media_crop_reports,
             'review_required_for_subject_focus_and_license':True},ensure_ascii=False,indent=2),
        encoding='utf-8')
    report={'status':'TECHNICAL_PASS' if frames/FPS<=brief['target_seconds']+5 or allow_longer else 'NEEDS_EDITORIAL_TRIM',
            'stage20_design_qa':'visual_design.json',
            'stage20_visual_style':design['visual_style'],
            'stage20_original_brand_assets_only':True,
            'stage18_voice_qa':'voice_qa.json',
            'stage18_word_alignment':'ESTIMATED_WITHIN_PIPER_CHUNK_NOT_FORCED',
            'stage19_smart_crop_opt_in':True,
            'remotion_frame_sampling_step':sample_every,'remotion_concurrency':concurrency,
            'motion_quality':('NATIVE_30FPS' if sample_every==1 else 'DEMO_STRESS_REPEATED_FRAMES_NOT_PRODUCTION'),
            'source_manifest':str(brief_file),'demo':bool(brief.get('demo')),
            'duration_seconds':round(frames/FPS,2),'target_seconds':brief['target_seconds'],
            'formats':output,'Piper_TTS':not silence,'claim_and_media_review_required':True,
            'human_publication_required':True}
    (root/'qa_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'sources.json').write_text(json.dumps([{'headline':x['headline'],'sources':x['sources']} for x in brief['stories']],ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'publishing_metadata.json').write_text(json.dumps({'title':brief.get('video_title',''),
            'description':brief.get('video_description',''),'hashtags':brief.get('hashtags',[])},ensure_ascii=False,indent=2),encoding='utf-8')
    rights=[]
    for i,story in enumerate(brief['stories'],1):
        for scene in story.get('visual_plan') or []:
            if scene.get('type') in ('licensed_image','licensed_broll'):
                rights.append({'story_index':i,'headline':story['headline'],
                               'media_path':scene.get('media_path'),
                               'media_sha256':scene.get('media_sha256'),
                               'source_url':scene.get('source_url'),
                               'license_name':scene.get('license_name'),
                               'author':scene.get('author'),
                               'attribution':scene.get('attribution'),
                               'license_evidence':scene.get('license_evidence'),
                               'requires_human_rights_review':True})
        if story.get('image_path'):
            rights.append({'story_index':i,'media_path':story['image_path'],
                           'license_evidence':story.get('image_license'),
                           'requires_human_rights_review':True})
    (root/'media_rights.json').write_text(json.dumps({'media':rights,'music_license':brief.get('music_license'),
               'music_path':brief.get('music_path'),'music_sha256':brief.get('music_sha256'),
               'rights_status':'REVIEW_REQUIRED_BEFORE_PUBLICATION'},ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    ap.add_argument('--aspect',choices=['9:16','16:9','both'])
    ap.add_argument('--voice')
    ap.add_argument('--encoder',choices=['auto','cpu','nvenc'],default='auto')
    ap.add_argument('--allow-demo',action='store_true')
    ap.add_argument('--demo-silence',action='store_true')
    ap.add_argument('--dry-run',action='store_true')
    ap.add_argument('--allow-longer',action='store_true')
    ap.add_argument('--music',type=Path)
    ap.add_argument('--speech-rate',type=float,default=1.0)
    ap.add_argument('--demo-sample-every',type=int,default=1)
    ap.add_argument('--lexicon',type=Path)
    args=ap.parse_args()
    brief_file=args.input.resolve()
    brief=json.loads(brief_file.read_text(encoding='utf-8-sig'))
    aspect=args.aspect or brief.get('aspect_ratio','9:16')
    if brief.get('aspect_ratio') and args.aspect and args.aspect!=brief['aspect_ratio']:
        raise ValueError('aspect override would change a previously approved manifest')
    if aspect not in ('9:16','16:9','both'):
        raise ValueError('invalid aspect ratio')
    # Renderer v0.3 verifies status, evidence, hash, and source approval.
    legacy.validate_brief(brief,args.allow_demo)
    if args.demo_sample_every not in (1,2,3,5,6,10) or (args.demo_sample_every>1 and brief.get('demo') is not True):
        raise ValueError('sampled-frame mode allowed only for DEMO stress tests')
    if args.demo_silence and brief.get('demo') is not True:
        raise ValueError('silent demo cannot process real approved news')
    lang=brief['language'].split('-')[0]
    voice=args.voice or ('vi_VN-vais1000-medium' if lang=='vi' else 'en_US-lessac-medium')
    if lang=='vi' and not voice.startswith('vi_') or lang=='en' and not voice.startswith('en_'):
        raise ValueError('voice language conflicts with script language')
    if args.music and (not args.music.is_file() or not brief.get('music_license')):
        raise ValueError('music missing or permission evidence missing')
    if not 0.75 <= args.speech_rate <= 1.35:
        raise ValueError('speech-rate must be in 0.75..1.35')
    music=approved_audio_asset(brief,brief_file.parent,'music',args.music)
    lexicon=approved_audio_asset(brief,brief_file.parent,'pronunciation_lexicon',args.lexicon)
    os.environ['PIPER_SPEECH_RATE']=str(args.speech_rate)
    os.environ.pop('PIPER_PRONUNCIATION_MAP',None)
    if lexicon:
        os.environ['PIPER_PRONUNCIATION_MAP']=str(lexicon)
    if args.dry_run:
        print(json.dumps({'valid':True,'aspect':aspect,'format_count':2 if aspect=='both' else 1,
                          'stories':len(brief['stories']),'demo':bool(brief.get('demo'))},ensure_ascii=False))
        return
    if args.out.exists():
        raise ValueError('output already exists: '+str(args.out))
    result=render(brief,brief_file,args.out.resolve(),aspect,voice,args.encoder,
                  args.demo_silence,music,args.allow_longer,args.demo_sample_every)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']!='TECHNICAL_PASS':
        raise RuntimeError('Video too long; editorial trim required')
if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError,KeyError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
        print('VIDEO_PIPELINE_ERROR: '+str(exc),file=sys.stderr)
        sys.exit(2)
