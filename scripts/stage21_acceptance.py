#!/usr/bin/env python3
"""Giai đoạn 21: kiểm toán phát hành candidate; Windows thứ hai chưa kiểm thử."""
import argparse,datetime as dt,json,os,re,subprocess,sys
from pathlib import Path
import release_audit,qa_engine as qa,job_integrity as integrity,render_video as renderer
ROOT=Path(__file__).resolve().parents[1]
RT=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(ROOT.parent/(ROOT.name+'-runtime'))))
BASE=RT/'stage21-validation-20261024'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def verify(out:Path,md:Path):
 if out.exists() or md.exists():raise FileExistsError('No acceptance overwrite')
 manifest=read(ROOT.parent/'skill-tintuc-backups'/'pre-stage21-20261024-1203.sha256.json')
 backup=ROOT.parent/'skill-tintuc-backups'/'pre-stage21-20261024-1203'
 if len(manifest)<75:raise ValueError('backup incomplete')
 for row in manifest:
  f=(backup/row['relative']).resolve()
  if not f.is_relative_to(backup.resolve()) or integrity.sha256(f).lower()!=row['sha256'].lower():
   raise ValueError('source backup SHA changed')
 scan=release_audit.audit(ROOT)
 if scan['issues']:raise ValueError('source audit failed: '+str(scan['issues']))
 t=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(ROOT/'tests'),'-q'],
   capture_output=True,text=True,timeout=120,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))
 m=re.search(r'Ran (\d+) tests',t.stderr+t.stdout)
 if t.returncode or not m or int(m.group(1))<160:raise RuntimeError('regression failed: '+t.stderr[-800:])
 clean=read(BASE/'cleanroom'/'cleanroom-doctor.json')
 if not clean['ready_dual_aspect'] or not clean['stage19_smart_crop']['opencv_local']:
  raise ValueError('cleanroom doctor did not pass')
 isolated=BASE/'cleanroom'/'AI-News-Video-Skill-runtime'
 for rel in ['.venv/Scripts/python.exe','models/vi_VN-vais1000-medium.onnx',
       'models/en_US-lessac-medium.onnx','remotion/node_modules/remotion',
       'tools/ffmpeg-selected/ffmpeg.exe']:
  if not (isolated/rel).exists():raise ValueError('isolated install missing '+rel)
 stab=read(BASE/'stability-injection'/'stage15_stability.json')
 if stab['status']!='STABILITY_QA_PASS' or set(stab['negative_tests'])!={'bad_srt','corrupt_video','deleted_video'}:
  raise ValueError('fault injection failed')
 approved=RT/'jobs'/'stage5-evidence72-20261024'/'approved.json'
 original_hash='c616ce6e38dceaf1af0fb364205f9f25efb71813bf88efdc7e7944fe97383d2b'
 if integrity.sha256(approved)!=original_hash:raise ValueError('approved altered')
 renderer.validate_brief(read(approved),False)
 old=RT/'deliveries'/'Tin-Cong-Nghe-My-20261024-60s'
 hand=read(old/'handoff_final.json')
 for f in hand['exports']:
  if integrity.sha256(old/f['filename'])!=f['sha256']:raise ValueError('old handoff changed')
 initial_failure=read(BASE/'qa_rejected_real_63s.json')
 if initial_failure.get('technical_pass') is not False or not all(x in initial_failure['errors'] for x in ('REAL_DURATION_OUTSIDE_5PCT:9:16','REAL_DURATION_OUTSIDE_5PCT:16:9')):
  raise RuntimeError('Original 63-second duration failure must be preserved as test evidence')
 new=BASE/'real_approved_rate107_CPU_native'
 raw=read(new/'qa_report.json')
 if raw['demo'] or raw['status']!='TECHNICAL_PASS':raise ValueError('real rerender incomplete')
 if Path(raw['source_manifest']).resolve()!=approved.resolve():raise ValueError('unapproved render source')
 qa_result=qa.analyze(new,BASE/'independent_real_qa.json','both',True)
 if qa_result['errors'] or not qa_result['technical_pass']:
  raise ValueError('real QA ERROR: '+repr(qa_result['errors']))
 formats=qa_result['formats']
 if set(formats)!={'9:16','16:9'}:raise ValueError('aspect mismatch')
 for aspect,info in formats.items():
  if abs(info['duration_seconds']-60)>3 or info['fps']!=30 or info['subtitles']['cues']<1:
   raise ValueError('real approved output violates timing/FPS/SRT')
  if integrity.sha256(new/info['video'])!=info['sha256']:
   raise ValueError('real video unexpectedly modified')
 (BASE/'independent_real_qa.json').write_text(json.dumps(qa_result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 previous=read(RT/'releases'/'AI-News-Video-Skill-v0.8.0-20261024.manifest.json')
 if integrity.sha256(RT/'releases'/'AI-News-Video-Skill-v0.8.0-20261024.zip')!=previous['zip_sha256']:
  raise ValueError('old release changed')
 stage20=read(RT/'stage20-validation-20261024'/'technical_acceptance.json')
 if stage20['status']!='TECHNICAL_ACCEPTANCE_PASS':raise ValueError('stage20 regressions not accepted')
 report={'status':'RELEASE_CANDIDATE_PENDING_SECOND_WINDOWS','phase':21,
  'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
  'regression_tests_passed':int(m.group(1)),
  'source_audit':'PASS','source_files':scan['source_file_count'],'python_ast':scan['python_ast_passed'],
  'baseline_sha256_files_verified':len(manifest),'stage20_presets_verified':True,
  'isolated_new_python_venv_and_npm_ci_same_host':'PASS',
  'bootstrap_existing_isolated_runtime':'PASS',
  'fresh_different_windows_pc_or_vm':'NOT_TESTED',
  'original_user_approval_sha256':original_hash,
  'old_handoff_files_unchanged':len(hand['exports']),
  'approved_real_pipeline_qa':qa_result['status'],
  'new_real_duration_seconds':{k:v['duration_seconds'] for k,v in formats.items()},
  'real_qa_warnings':qa_result['warnings'],
  'stability_fault_cases':list(stab['negative_tests']),
  'stress_demo_duration_outside_5pct':[{'target':p['target_s'],'actual':p['actual_s']}
    for p in stab['native_profiles'] if not p['within_five_percent']],
  'previous_zip_unchanged':True,
  'stage21_items':{'21.01':'PASS','21.02':'PASS','21.03':'PASS','21.04':'PASS',
      '21.05':'PASS','21.06':'PARTIAL_SAME_WINDOWS_HOST',
      '21.07':'SOURCE_PACKAGE_READY','21.08':'RELEASE_CANDIDATE_ONLY'},
  'no_auto_upload':True,'human_review_required':True,
  'blockers_for_general_availability':['Need a second independently installed clean Windows PC or Windows VM test.']}
 out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 lines=['# Báo cáo Giai đoạn 21 — nghiệm thu ứng viên v1.0.0-rc.2',
  '', '**RELEASE_CANDIDATE_PENDING_SECOND_WINDOWS** — '+report['checked_at'],
  '', '- Tổng số kiểm thử: '+str(report['regression_tests_passed'])+' PASS; source audit PASS; backup '+str(len(manifest))+' tệp đúng SHA.',
  '- Đã cài lại venv Python + pip + npm ci Remotion và kiểm tra bootstrap trong thư mục tách biệt cùng Windows.',
  '- Tin thật 2 sự kiện có phê duyệt thực tế đã render mới cả 9:16/16:9, QA độc lập 0 lỗi, '
        +str(report['new_real_duration_seconds'])+' giây, H264/AAC 30 FPS, SRT và Piper.',
  '- '+str(len(hand['exports']))+' file bàn giao cũ nguyên hash. Không chỉnh approved.json.',
  '- Fault-injection SRT hỏng/MP4 hỏng/mất MP4 đạt; kiểm tra lock và hash đã có unit test.',
  '- Các DEMO stress cũ 30/60/90/180 không đạt ±5% dù codec QA PASS, không được coi là mẫu đúng độ dài.',
  '- Metadata cũ có câu "bản nháp chờ duyệt" sẽ phải sửa thủ công khi tự đăng, không ghi đè approved content.',
  '- Không tự cấp phép media, không tự đăng TikTok/YouTube; người dùng kiểm lại nội dung, nguồn, giọng đọc và bản quyền.',
  '', '## Điều kiện còn thiếu trước khi phát hành v1.0.0 GA',
  '21.06: cài sạch trên một máy Windows hoặc VM Windows thứ hai độc lập, chạy bootstrap, doctor, tests, render DEMO cả hai tỷ lệ, QA và lưu SHA256.',
  'Windows Sandbox trên ADMIN-PC-02 hiện Disabled; repl khác online chạy Linux. Không nhận cleanroom cùng-host là một máy thứ hai.',
  '', '## Kết luận',
  'Hoàn tất kiểm toán và phát hành RELEASE CANDIDATE v1.0.0-rc.2. Không ghi GA khi 21.06 chưa được thử đầy đủ.',
  '', 'Checklist: references/STAGE21_RELEASE_CHECKLIST.md','QA: '+str(BASE/'independent_real_qa.json'),
  'Acceptance: '+str(out),'']
 md.parent.mkdir(parents=True,exist_ok=True);md.write_text('\n'.join(lines),encoding='utf-8')
 return report
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--out',type=Path,required=True)
 p.add_argument('--markdown',type=Path,required=True)
 a=p.parse_args();r=verify(a.out,a.markdown)
 print(json.dumps({'status':r['status'],'tests':r['regression_tests_passed'],
   'real_durations':r['new_real_duration_seconds'],'stage21_items':r['stage21_items']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
