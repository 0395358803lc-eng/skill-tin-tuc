#!/usr/bin/env python3
"""Strict Stage20 end-to-end visual-presets acceptance on authorized local Windows runtime."""
import argparse,ast,datetime as dt,json,os,re,subprocess,sys
from pathlib import Path
import qa_engine as qa
import job_integrity as ji

SKILL=Path(__file__).resolve().parents[1]
RT=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(SKILL.parent/(SKILL.name+'-runtime'))))
ROOT=RT/'stage20-validation-20261024'
BACKUP=SKILL.parent/'skill-tintuc-backups'/'pre-stage20-20261024-1135'
CASES=[
 ('quick','vi-VN',15,'quick_15s_vi_VN','quick_15s_vi_VN'),
 ('roundup','vi-VN',30,'roundup_30s_vi_VN','roundup_30s_vi_VN'),
 ('deep_dive','en-US',15,'deep_dive_15s_en_US_adjusted','deep_dive_15s_en_US_v3'),
]
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def verify(out,md):
 if out.exists() or md.exists():raise FileExistsError('No overwrite of Stage20 acceptance')
 manifest=read(BACKUP/'manifest.json')
 if len(manifest)<55:raise ValueError('Backup incomplete')
 for f in manifest:
  path=(BACKUP/f['relative']).resolve()
  if not path.is_relative_to(BACKUP.resolve()) or ji.sha256(path).lower()!=f['sha256'].lower():
   raise ValueError('Backup SHA-256 mismatch: '+str(path))
 source=list((SKILL/'scripts').glob('*.py'))+list((SKILL/'tests').glob('*.py'))
 for file in source:ast.parse(file.read_text(encoding='utf-8-sig'))
 t=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(SKILL/'tests'),'-q'],
   capture_output=True,text=True,timeout=120,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
 match=re.search(r'Ran (\d+) tests',t.stderr+t.stdout)
 if t.returncode or not match or int(match.group(1))<143:
  raise ValueError('Regression tests not all passing: '+t.stderr[-900:])
 review=read(ROOT/'visual_review.json')
 if review.get('inspected') is not True or review.get('deep_dive_horizontal_overlap_fixed') is not True:
  raise ValueError('Visual defect has not been reviewed and resolved')
 output=[]
 for style,language,target,fixture_name,render_name in CASES:
  folder=ROOT/'renders'/render_name
  input_manifest=read(ROOT/'fixtures'/(fixture_name+'.json'))
  orig_report=read(folder/'qa_report.json')
  if not input_manifest.get('demo') or input_manifest.get('visual_style')!=style or input_manifest.get('language')!=language:
   raise ValueError('wrong DEMO fixture for '+style)
  if (orig_report['motion_quality']!='NATIVE_30FPS' or
      orig_report['status']!='TECHNICAL_PASS' or
      orig_report.get('stage20_visual_style')!=style):
   raise ValueError('render not valid production-native output for '+style)
  target_qa=ROOT/'final_qa'/('qa-'+style+'.json')
  if target_qa.exists():raise FileExistsError('QA report exists: '+str(target_qa))
  quality=qa.analyze(folder,target_qa,'both',True)
  if quality['errors'] or quality['technical_pass'] is not True:
   raise ValueError('Independent QA failed: '+style+': '+str(quality['errors']))
  target_qa.parent.mkdir(parents=True,exist_ok=True)
  target_qa.write_text(json.dumps(quality,ensure_ascii=False,indent=2),encoding='utf-8')
  if set(quality['formats'])!={'9:16','16:9'}:
   raise ValueError('Missing aspect ratio: '+style)
  actual=sum(row['duration_seconds'] for row in quality['formats'].values())/2
  if abs(actual-target)>target*.05:
   raise ValueError('Target duration outside +/-5pct: '+style+' '+str(actual))
  for aspect,row in quality['formats'].items():
   if row['fps']!=30 or row['subtitles']['cues']<1 or row['subtitles']['caption_coverage_ratio']<.6:
    raise ValueError('Video or SRT mismatch: '+style+'/'+aspect)
   if ji.sha256(folder/row['video'])!=row['sha256']:
    raise ValueError('Video fingerprint mismatch: '+style+'/'+aspect)
  perf=read(ROOT/'benchmarks'/(render_name+'.json'))
  if perf['returncode']!=0 or perf.get('timeout') or perf.get('remotion_sample_every')!=1:
   raise ValueError('Performance run failed: '+style)
  info=read(folder/'visual_design.json')
  if info['visual_style']!=style:raise ValueError('Wrong original approved design: '+style)
  output.append({'preset':style,'language':language,'target_seconds':target,
    'duration_seconds':round(actual,3),
    'duration_error_pct':round(100*(actual/target-1),2),
    'story_count':len(input_manifest['stories']),
    'render_walltime_seconds':perf['elapsed_seconds'],
    'peak_process_tree_rss_mb':perf['peak_process_tree_rss_mb'],
    'peak_gpu_device_used_mb':perf['peak_gpu_used_mb'],
    'native_30fps':True,
    'codec':'H264/AAC','encoder':orig_report['formats']['9:16']['qa']['encoder'],
    'sha256_mp4':{ratio:row['sha256'] for ratio,row in quality['formats'].items()},
    'qa_status':quality['status'],'qa_warnings':quality['warnings'],
    'output':str(folder)})
 p1=read(ROOT/'benchmarks'/'quick_15s_vi_VN_concurrency1.json')
 p2=read(ROOT/'benchmarks'/'quick_15s_vi_VN.json')
 if any(p['returncode']!=0 or p.get('timeout') for p in (p1,p2)):
  raise ValueError('Concurrency benchmark incomplete')
 if p1['remotion_concurrency']!=1 or p2['remotion_concurrency']!=2:
  raise ValueError('Concurrency benchmark configuration mismatch')
 ab={'one_worker_wall_seconds':p1['elapsed_seconds'],
     'two_workers_wall_seconds':p2['elapsed_seconds'],
     'one_worker_peak_rss_mb':p1['peak_process_tree_rss_mb'],
     'two_workers_peak_rss_mb':p2['peak_process_tree_rss_mb'],
     'faster_in_single_run':1 if p1['elapsed_seconds']<p2['elapsed_seconds'] else 2,
     'caveat':'One measurement per setting under variable machine load, not statistically conclusive.'}
 prior=RT/'jobs'/'stage5-evidence72-20261024'/'approved.json'
 approval='c616ce6e38dceaf1af0fb364205f9f25efb71813bf88efdc7e7944fe97383d2b'
 if ji.sha256(prior)!=approval:raise ValueError('Previous user approved script altered')
 delivery=RT/'deliveries'/'Tin-Cong-Nghe-My-20261024-60s'
 old=read(delivery/'handoff_final.json')
 if not all(ji.sha256(delivery/x['filename'])==x['sha256'] for x in old['exports']):
  raise ValueError('Old approved news deliverables changed')
 release=read(RT/'releases'/'AI-News-Video-Skill-v0.7.0-20261024.manifest.json')
 if ji.sha256(RT/'releases'/'AI-News-Video-Skill-v0.7.0-20261024.zip')!=release['zip_sha256']:
  raise ValueError('Previous v0.7.0 release modified')
 skill_files=[x for x in SKILL.rglob('*') if x.is_file()]
 if any(x.suffix.lower() in ('.mp4','.wav','.pyc','.onnx','.zip','.exe','.log','.db')
        for x in skill_files):
  raise ValueError('Runtime artifact polluted portable Skill source')
 record={'status':'TECHNICAL_ACCEPTANCE_PASS','stage':20,
   'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
   'unit_tests_passed':int(match.group(1)),'python_ast_files_passed':len(source),
   'backed_up_files_verified':len(manifest),
   'preset_results':output,'concurrency_ab':ab,
   'initial_deep_dive_layout_failure_retained':True,
   'original_approved_script_sha256':approval,
   'old_delivery_files_unchanged':len(old['exports']),
   'old_release_v070_checksum_unchanged':True,
   'visual_review':review,
   'all_video_files_are_demo_not_for_publication':True,
   'no_auto_post':True,
   'stage21_still_open':True,
   'limitations':['Automated QA cannot guarantee no visual overlap in every frame.',
      'Presets were tested as synthetic videos, not additional real news.',
      'Human review remains required for factual reliability, copyright, voice and visual quality.',
      'Performance A/B on this machine only; GPU utilization includes background loads.']}
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 rows=['# Nghiệm thu Đợt 8 — Giai đoạn 20',
   '', 'Kết quả: TECHNICAL_ACCEPTANCE_PASS, '+record['checked_at'],
   '',str(record['unit_tests_passed'])+'/'+str(record['unit_tests_passed'])+' kiểm thử đạt; '+str(len(manifest))+' tệp sao lưu SHA-256 đúng.',
   '','## Video DEMO dựng thực tế', '',
   '| Phong cách | Ngôn ngữ | Tin | Thời lượng | Sai lệch | Dựng hai tỷ lệ | RAM đỉnh | QA |',
   '|---|---|---:|---:|---:|---:|---:|---|']
 for row in output:
  rows.append('| '+row['preset']+' | '+row['language']+' | '+str(row['story_count'])+
   ' | '+str(row['duration_seconds'])+'s | '+str(row['duration_error_pct'])+
   '% | '+str(row['render_walltime_seconds'])+'s | '+str(row['peak_process_tree_rss_mb'])+' MB | PASS |')
 rows+=['','Tất cả sáu MP4 chính có native 30 FPS, 1080x1920 và 1920x1080, H264/AAC, âm thanh Piper và SRT.',
   '', '## Hạng mục 20.01–20.08',
   '- 20.01: Bộ nhận diện AI NEWS VIDEO gốc bằng CSS/vector, ba palette, font hệ thống.',
   '- 20.02: Ba preset quick, roundup, deep_dive; visual_style nằm trong draft và SHA-256 approval.',
   '- 20.03: Intro/outro trên timeline hiện tại, không thêm lời đọc hoặc độ dài.',
   '- 20.04: Fade/slide theo story, nhịp 9/12/15 frame tùy preset.',
   '- 20.05: Infographic từ approved data_points 0..100, có hình kiểm tra 9:16 và 16:9.',
   '- 20.06: Guard vùng an toàn, validation chữ dài, và sửa lỗi tiêu đề ngang deep_dive sau khi xem MP4 v1.',
   '- 20.07: Kiểm tiếng Việt/Anh, Unicode, headline dài, các cảnh không chồng, 143 bài hồi quy và QA độc lập.',
   '- 20.08: Benchmark trên GTX 1060 3GB, concurrency=1 và 2 với cùng brief.',
   '', '## Hiệu năng trên máy kiểm thử',
   '- Concurrency 1: '+str(ab['one_worker_wall_seconds'])+' giây, RAM '+str(ab['one_worker_peak_rss_mb'])+' MB.',
   '- Concurrency 2: '+str(ab['two_workers_wall_seconds'])+' giây, RAM '+str(ab['two_workers_peak_rss_mb'])+' MB.',
   '- Kết quả nhanh hơn một lượt: '+str(ab['faster_in_single_run'])+'. Không suy rộng cho tất cả máy.',
   '', '## Lỗi phát hiện và khắc phục',
   '- Lần render deep_dive đầu tiên ở 16:9 có headline tiếng Anh dài che phần tóm tắt và subtitle.',
   '- V2 điều chỉnh kích thước headline/summary cho vùng chart, không còn chồng chữ trong frame kiểm tra.',
   '- V3 sử dụng DEMO đã chỉnh thời lượng lời đọc; v1/v2 giữ riêng làm bằng chứng, không ghi đè.',
   '', '## An toàn và giới hạn',
   '- Bản tin thật Giai đoạn 14: approved hash không đổi; '+str(len(old['exports']))+' tệp bàn giao không đổi.',
   '- v0.7.0 release cũ và '+str(len(manifest))+' tệp baseline backup không đổi.',
   '- Không dùng nội dung DEMO làm tin thật, không tự đăng TikTok/YouTube.',
   '- QA tự động không chứng minh quyền thương mại, đúng sự kiện hay chất lượng thị giác mọi frame.',
   '- V1.0.0 vẫn cần Giai đoạn 21, bao gồm clean-install và nghiệm thu tổng thể.',
   '', 'Bằng chứng: '+str(out),
   'Hướng dẫn: references/STAGE20_OPERATIONS.md','']
 md.parent.mkdir(parents=True,exist_ok=True)
 md.write_text('\n'.join(rows),encoding='utf-8')
 return record
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--out',required=True,type=Path)
 p.add_argument('--markdown',required=True,type=Path)
 a=p.parse_args()
 record=verify(a.out,a.markdown)
 print(json.dumps({'status':record['status'],'tests':record['unit_tests_passed'],
  'presets':[{'preset':p['preset'],'mp4_duration':p['duration_seconds'],'render_seconds':p['render_walltime_seconds']} for p in record['preset_results']],
  'verified_backup_files':record['backed_up_files_verified']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
