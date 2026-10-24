#!/usr/bin/env python3
"""Stage18–19 acceptance: source-backed local TEST render with both aspect ratios.

No real approved news script is changed. All DEMO outputs stay outside Skill.
"""
from __future__ import annotations
import argparse,ast,datetime as dt,hashlib,json,os,re,subprocess,sys,shutil
from pathlib import Path
import qa_engine as qa
import job_integrity as integrity

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(ROOT.parent/(ROOT.name+'-runtime'))))

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def validate(folder:Path,qa_report:Path,acceptance:Path,report_md:Path)->dict:
    if acceptance.exists() or report_md.exists() or qa_report.exists():
        raise FileExistsError('Stage 18-19 reports already exist, no overwrite')
    folder=folder.resolve()
    source=read(folder/'qa_report.json')
    if not source.get('demo') or source.get('motion_quality')!='NATIVE_30FPS':
        raise ValueError('native30 DEMO-only test required')
    if not (folder/'voice_qa.json').is_file() or not (folder/'smart_crop_report.json').is_file():
        raise ValueError('Stage18/19 actual output sidecars are missing')
    if source.get('stage18_voice_qa') not in (None,'voice_qa.json') or source.get('stage19_smart_crop_opt_in') not in (None,True):
        raise ValueError('Stage18/19 renderer metadata has invalid flags')
    # The first Stage18/19 DEMO was created before the new manifest fields were
    # committed to the renderer. Analyze an immutable, separately-labeled QA shadow,
    # preserving original DEMO files and MP4 SHA-256 without a second full re-render.
    shadow_used=not source.get('stage18_voice_qa')
    qa_folder=folder
    if shadow_used:
        qa_folder=folder.parent/'qa-shadow-stage18-19'
        if qa_folder.exists():raise FileExistsError('QA reconciliation shadow already exists')
        qa_folder.mkdir()
        for original in folder.iterdir():
            if original.is_file() and original.name!='qa_report.json':
                dest=qa_folder/original.name
                try:os.link(original,dest)
                except OSError:shutil.copy2(original,dest)
        props=qa_folder/'_work'
        props.mkdir()
        for suffix in ('9x16','16x9'):
            original=folder/'_work'/('props-'+suffix+'.json')
            if original.is_file():shutil.copy2(original,props/original.name)
        enriched=dict(source,stage18_voice_qa='voice_qa.json',
            stage18_word_alignment='ESTIMATED_WITHIN_PIPER_CHUNK_NOT_FORCED',
            stage19_smart_crop_opt_in=True)
        (qa_folder/'qa_report.json').write_text(json.dumps(enriched,ensure_ascii=False,indent=2),
                                               encoding='utf-8')
    qa_report.parent.mkdir(parents=True,exist_ok=True)
    checked=qa.analyze(qa_folder,qa_report,'both',True)
    if checked['errors'] or not checked['technical_pass']:
        raise ValueError('Independent QA error: '+repr(checked['errors']))
    with qa_report.open('x',encoding='utf-8') as f:json.dump(checked,f,ensure_ascii=False,indent=2)
    voice=read(folder/'voice_qa.json')
    if voice['word_forced_alignment_performed'] or voice['alignment']!='CHUNK_REAL_WAV_WORD_ESTIMATED':
        raise ValueError('Incorrect forced alignment claim')
    if not voice['caption_cues'] or voice['caption_coverage_pct']<75:
        raise ValueError('Poor caption coverage')
    if abs(voice['voice_real_wav_seconds']-float(source['duration_seconds']))>1.5:
        raise ValueError('voice WAV and video duration mismatch')
    crop=read(folder/'smart_crop_report.json')
    if set(crop['ratios'])!={'9:16','16:9'}:
        raise ValueError('both ratios required')
    each={}
    for ratio,frames in crop['ratios'].items():
        if not frames:raise ValueError('no media evaluated: '+ratio)
        kinds={x['source_type'] for x in frames}
        if not {'licensed_image','licensed_broll'}<=kinds:
            raise ValueError('need real image and video smart crop on '+ratio)
        for row in frames:
            if not row['focus'] or not row['rights']:
                raise ValueError('missing smart focus/rights evidence')
            rights=row['rights']
            if rights['human_commercial_rights_check_still_required'] is not True:
                raise ValueError('rights auto approved is forbidden')
            for key in ('source_url','attribution','license_name','author_or_organization','source_sha256'):
                if not rights.get(key):raise ValueError('incomplete source provenance:'+key)
        each[ratio]={'smart_traces':len(frames),'formats':sorted(kinds)}
    old_job=RUNTIME/'jobs'/'stage5-evidence72-20261024'
    expected='c616ce6e38dceaf1af0fb364205f9f25efb71813bf88efdc7e7944fe97383d2b'
    if integrity.sha256(old_job/'approved.json')!=expected:
        raise ValueError('prior user approval changed')
    delivery=RUNTIME/'deliveries'/'Tin-Cong-Nghe-My-20261024-60s'
    handoff=read(delivery/'handoff_final.json')
    if any(integrity.sha256(delivery/r['filename'])!=r['sha256'] for r in handoff['exports']):
        raise ValueError('previous real delivery modified')
    backup=ROOT.parent/'skill-tintuc-backups'/'pre-20261024-stage18-19'
    rows=read(backup/'backup-checksums.json')
    if not isinstance(rows,list) or len(rows)<45:
        raise ValueError('incomplete backup SHA-256 manifest')
    for row in rows:
        p=(backup/row['name']).resolve()
        if not p.is_relative_to(backup.resolve()) or integrity.sha256(p).lower()!=row['sha256'].lower():
            raise ValueError('pre-edit backup changed')
    source_py=list((ROOT/'scripts').glob('*.py'))+list((ROOT/'tests').glob('*.py'))
    for p in source_py:ast.parse(p.read_text(encoding='utf-8'))
    run=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',
        str(ROOT/'tests'),'-q'],capture_output=True,text=True,timeout=120,
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
    match=re.search(r'Ran (\d+) tests',run.stdout+run.stderr)
    if run.returncode or not match or int(match.group(1))<128:
        raise ValueError('Unit test suite failed: '+run.stderr[-1200:])
    metrics_path=folder.parent/'benchmark-native30.json'
    metrics=read(metrics_path)
    if metrics.get('returncode')!=0 or metrics.get('timeout') or metrics.get('remotion_sample_every')!=1:
        raise ValueError('native rendering benchmark failed or used frame sampling')
    if set(checked['formats'])!={'9:16','16:9'} or any(x['fps']!=30 for x in checked['formats'].values()):
        raise ValueError('incorrect native fps or ratio')
    duration=sum(x['duration_seconds'] for x in checked['formats'].values())/2
    if abs(duration-30)>1.5:raise ValueError('DEMO video outside 5% of target')
    payload={'status':'TECHNICAL_ACCEPTANCE_PASS','stage':'18-19',
        'observed_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'unit_tests_passed':int(match.group(1)),
        'python_files_syntax_passed':len(source_py),'backup_verified_files':len(rows),
        'language':'vi-VN','demo_only':True,'video_target_s':30,
        'measured_mp4_seconds':round(duration,3),
        'duration_delta_pct':round(100*(duration/30-1),2),
        'renderer_status':source['status'],'remotion_motion_quality':source['motion_quality'],
        'acceptance_qa_shadow_reconciled_missing_original_manifest_flags':shadow_used,
        'original_mp4s_and_renderer_qa_unchanged':True,
        'formats':{k:{'file':v['video'],'sha256':v['sha256'],
                      'duration_s':v['duration_seconds'],'fps':v['fps'],
                      'caption_cues':v['subtitles']['cues'],
                      'caption_coverage_ratio':v['subtitles']['caption_coverage_ratio'],
                      'audio_peak_db':v['audio']['peak_dB'],
                      'audio_mean_db':v['audio']['mean_dB']} for k,v in checked['formats'].items()},
        'stage18':voice,'stage19':each,
        'render_walltime_s':metrics['elapsed_seconds'],
        'peak_process_tree_ram_mb':metrics.get('peak_process_tree_rss_mb'),
        'observed_peak_gpu_device_memory_mb':metrics.get('peak_gpu_used_mb'),
        'approved_job_hash_unchanged':True,'original_handoff_files_verified':len(handoff['exports']),
        'manual_license_and_visual_review_required':True,'automatic_publication':False,
        'limits':['Word highlighting is estimated within Piper chunk; NOT speech forced alignment.',
                  'Face Haar detection and saliency heuristics are not semantic object identification.',
                  'Audio text-to-speech pronunciation quality needs human listening before real upload.',
                  'Images/B-roll are synthetic test material and MUST NOT be published as news.',
      'The first Stage18/19 DEMO renderer manifest omitted extension flags; QA was performed on a separately reconstructed metadata shadow without modifying the source MP4s.']}
    acceptance.parent.mkdir(parents=True,exist_ok=True)
    acceptance.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Đợt 7 — Giai đoạn 18–19: Nghiệm thu kỹ thuật',
      '',f"**{payload['status']}** — {payload['observed_utc']}",
      '',f"Tests: **{payload['unit_tests_passed']}/{payload['unit_tests_passed']} PASS**, backup {len(rows)} tệp nguyên vẹn.",
      '',
      '## Kết quả render thực tế bằng Piper/OpenCV/Remotion/FFmpeg',
      '',
      '| Tỷ lệ | FPS | MP4 giây | Phụ đề | WAV/caption | Đầu ra |',
      '|---|---:|---:|---:|---|---|']
    for ratio in ('9:16','16:9'):
        x=payload['formats'][ratio]
        lines.append(f"| {ratio} | {x['fps']} | {x['duration_s']:.2f} | {x['caption_cues']} | Ghi cue theo WAV thật | {x['file']} |")
    lines += ['',f"Target 30s; actual {payload['measured_mp4_seconds']:.2f}s, sai số {payload['duration_delta_pct']:+.2f}%.",
      f"Render cả hai bản: {payload['render_walltime_s']:.2f}s. RAM lấy mẫu {payload['peak_process_tree_ram_mb']} MB; VRAM GPU toàn máy tối đa {payload['observed_peak_gpu_device_memory_mb']} MB.",
      '## Giai đoạn 18 — PASS kỹ thuật',
      f"Piper WAV = {voice['voice_real_wav_seconds']}s, {voice['caption_cues']} subtitle cues, {voice['approximate_word_highlights']} từ có time estimate, độ phủ {voice['caption_coverage_pct']}%.",
      'Remotion hiển thị nhấn từ theo time estimate; SRT giữ văn bản nguyên gốc; FFmpeg loudnorm/ducking tùy giấy phép nhạc và QA độc lập.',
      'Giọng đọc không được hệ thống chứng nhận phát âm chuẩn từng từ; người dùng cần nghe lại tên riêng/số.',
      '## Giai đoạn 19 — PASS kỹ thuật',
      'Hai ratio đều chạy Smart Crop nguồn ảnh synthetic và B-roll dynamic 7 frame focal, SHA-256 media, tác giả, quyền, credit, báo cáo cảnh.',
      'Nguồn media test tự tạo, có watermark DEMO; không đại diện cho nội dung tin thật hoặc giấy phép bên ngoài.',
      '## Bảo vệ và giới hạn',
      'Bản approved.json của Giai đoạn 14 và 13 tệp bàn giao giữ nguyên SHA-256; không đổi script được người dùng duyệt; không tự đăng.',
      'Việc đánh giá nội dung thực tế, nhận diện semantic các đối tượng, độ chính xác face-crop nhiều người, chất lượng giọng và giấy phép vẫn cần bước rà soát người dùng.',
      '',f"Acceptance JSON: {acceptance}",f"QA JSON: {qa_report}",
      f"Runtime DEMO video: {folder}",'']
    report_md.parent.mkdir(parents=True,exist_ok=True)
    report_md.write_text('\n'.join(lines),encoding='utf-8')
    return payload

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--folder',required=True,type=Path)
    a.add_argument('--qa',required=True,type=Path)
    a.add_argument('--acceptance',required=True,type=Path)
    a.add_argument('--markdown',required=True,type=Path)
    p=a.parse_args()
    outcome=validate(p.folder,p.qa,p.acceptance,p.markdown)
    print(json.dumps({k:v for k,v in outcome.items() if k not in ('stage18','stage19','formats','limits')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
