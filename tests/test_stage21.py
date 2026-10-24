"""Stage21 portable audit, dual human-gates and no-unsafe-publication regression."""
from __future__ import annotations
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import release_audit as audit
import editorial_core as core
import studio_design as styles
from test_editorial import bundle,script,NOW

class Stage21ReleaseTests(unittest.TestCase):
 def test_current_skill_tree_has_no_runtime_media_or_secrets(self):
  result=audit.audit(ROOT)
  self.assertEqual(result['status'],'SOURCE_AUDIT_PASS',result['issues'])
  self.assertGreater(result['python_ast_passed'],25)
  self.assertGreater(result['source_file_count'],65)
 def test_source_audit_catches_binary_and_missing_core(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)
   (folder/'video.mp4').write_bytes(b'not a safe source artifact')
   result=audit.audit(folder)
   self.assertEqual(result['status'],'SOURCE_AUDIT_FAIL')
   self.assertTrue(any(x['code']=='NONPORTABLE_ARTIFACT' for x in result['issues']))
   self.assertTrue(any(x['code']=='MISSING_REQUIRED' for x in result['issues']))
 def test_audit_detects_private_key_fixture_without_secret_leak(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)
   (folder/'config.txt').write_text('-----BEGIN '+'PRIVATE KEY-----'+'not real',encoding='utf-8')
   result=audit.audit(folder)
   self.assertTrue(any(x['code']=='PRIVATE_KEY' for x in result['issues']))
 def test_release_audit_does_not_create_artifacts_in_source(self):
  before={x.relative_to(ROOT) for x in ROOT.rglob('*') if x.is_file()}
  result=audit.audit(ROOT)
  after={x.relative_to(ROOT) for x in ROOT.rglob('*') if x.is_file()}
  self.assertEqual(before,after)
  self.assertTrue(result['no_publication_integration_claimed'])
 def test_dependencies_include_benchmark_and_smart_crop_packages(self):
  normal=(ROOT/'requirements.txt').read_text(encoding='utf-8')
  smart=(ROOT/'requirements-smart-crop.txt').read_text(encoding='utf-8')
  self.assertIn('psutil',normal)
  self.assertIn('piper-tts',normal)
  self.assertIn('opencv-python-headless',smart)
 def test_portable_launcher_rejects_unsafe_existing_runtime(self):
  installer=(ROOT/'scripts'/'bootstrap_windows.ps1').read_text(encoding='utf-8')
  self.assertIn('AcceptExistingRuntime',installer)
  self.assertIn('Runtime cannot be nested inside Skill',installer)
  self.assertIn('will not',installer.lower())
 def test_style_and_narration_in_same_approval_fingerprint(self):
  b=bundle();choice=core.choose(b,core.check_bundle(b),['EVENT-01'],'Synthetic test selector',NOW)
  sc=script();sc['visual_style']='quick'
  draft=core.draft_manifest(b,choice,sc)
  approved=core.approve_draft(draft,{'confirmed_at':NOW,
   'user_confirmation':'Synthetic approval in isolated unit test only',
   'script_sha256':core.canonical_hash(draft),
   'approved_story_ids':['EVENT-01']})
  self.assertEqual(approved['aspect_ratio'],'both')
  self.assertEqual(approved['visual_style'],'quick')
  self.assertTrue(approved['stories'][0]['approved'])
  changed=copy.deepcopy(draft)
  changed['visual_style']='roundup'
  with self.assertRaises(ValueError):
   core.approve_draft(changed,{'confirmed_at':NOW,
      'user_confirmation':'Synthetic test only',
      'script_sha256':core.canonical_hash(draft),
      'approved_story_ids':['EVENT-01']})
 def test_unapproved_story_selection_is_rejected(self):
  b=bundle()
  with self.assertRaises(ValueError):
   core.choose(b,core.check_bundle(b),['EVENT-01'],'',NOW)
 def test_source_score_is_not_claimed_as_automated_truth(self):
  b=bundle()
  report=core.check_bundle(b)
  self.assertEqual(report['eligible_count'],1)
  self.assertFalse(report['story_reports'][0]['factually_verified_by_software'])
 def test_preset_does_not_change_user_script_or_fact_text(self):
  b={'language':'vi-VN','visual_style':'deep_dive',
    'target_seconds':60,'aspect_ratio':'both',
    'stories':[{'headline':'Tin giả lập','summary':'Chỉ dành kiểm tra.',
        'narration':'Không là tin thật','visual_plan':[{'type':'news_card'}]}]}
  old=json.dumps(b,ensure_ascii=False,sort_keys=True)
  self.assertEqual(styles.validate(b)['visual_style'],'deep_dive')
  self.assertEqual(json.dumps(b,ensure_ascii=False,sort_keys=True),old)
 def test_stage21_no_auto_posting_api(self):
  documents=(ROOT/'SKILL.md').read_text(encoding='utf-8')
  self.assertIn('Không đăng video tự động',documents)
  code=(ROOT/'scripts'/'workflow.py').read_text(encoding='utf-8')
  self.assertIn('ready_for_publication\":False',code)
  self.assertNotIn('tiktok/upload',code.lower())
 def test_bootstrap_is_explicit_about_separately_licensed_media(self):
  code=(ROOT/'scripts'/'bootstrap_windows.ps1').read_text(encoding='utf-8')
  self.assertIn('FFmpegSource',code)
  self.assertIn('VoiceModelsSource',code)
  self.assertNotIn('Invoke-WebRequest',code)
 def test_no_direct_media_or_models_in_portable_skill(self):
  result=audit.audit(ROOT)
  self.assertFalse(any(x['code']=='NONPORTABLE_ARTIFACT' for x in result['issues']))
 def test_real_video_outside_five_percent_is_not_technically_passed(self):
  import qa_engine as q
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)
   (folder/'clip.mp4').write_bytes(b'X'*1200)
   (folder/'qa_report.json').write_text(json.dumps({
      'demo':False,'status':'TECHNICAL_PASS','duration_seconds':56.,
      'target_seconds':60,'formats':{'9:16':{'file':'clip.mp4'}},
      'Piper_TTS':True}),encoding='utf-8')
   info={'streams':[{'codec_type':'video','width':1080,'height':1920,
        'codec_name':'h264','avg_frame_rate':'30/1'},
       {'codec_type':'audio','codec_name':'aac'}],
       'format':{'duration':'56.0'}}
   sound={'peak_dB':-2.,'mean_dB':-15.,
          'longest_silence_seconds':0.}
   with patch.object(q,'probe',return_value=info),patch.object(q,'audio_scan',return_value=sound):
    result=q.analyze(folder,folder/'unused.json','9:16',False)
   self.assertIn('REAL_DURATION_OUTSIDE_5PCT:9:16',result['errors'])
   self.assertFalse(result['technical_pass'])
 def test_demo_duration_is_warning_not_auto_publication(self):
  import qa_engine as q
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp)
   (folder/'clip.mp4').write_bytes(b'X'*1200)
   (folder/'qa_report.json').write_text(json.dumps({
      'demo':True,'status':'TECHNICAL_PASS','duration_seconds':50.,
      'target_seconds':60,'formats':{'9:16':{'file':'clip.mp4'}},
      'Piper_TTS':True}),encoding='utf-8')
   info={'streams':[{'codec_type':'video','width':1080,'height':1920,
        'codec_name':'h264','avg_frame_rate':'30/1'},
       {'codec_type':'audio','codec_name':'aac'}],
       'format':{'duration':'50.0'}}
   sound={'peak_dB':-2.,'mean_dB':-15.,
          'longest_silence_seconds':0.}
   with patch.object(q,'probe',return_value=info),patch.object(q,'audio_scan',return_value=sound):
    result=q.analyze(folder,folder/'unused.json','9:16',False)
   self.assertNotIn('REAL_DURATION_OUTSIDE_5PCT:9:16',result['errors'])
   self.assertIn('DEMO_NOT_FOR_PUBLICATION',result['warnings'])
   self.assertFalse(result['eligible_for_automatic_publication'])
 def test_no_source_mutation_from_editorial_hash(self):
  b=bundle();choice=core.choose(b,core.check_bundle(b),['EVENT-01'],'Synthetic selection',NOW)
  draft=core.draft_manifest(b,choice,script())
  first=core.canonical_hash(draft)
  self.assertEqual(first,core.canonical_hash(draft))
  self.assertNotIn('approval_record',draft)

if __name__=='__main__':unittest.main()
