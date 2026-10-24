"""Stage 4 offline regression tests for media, voice, captions and isolation.

Uses synthetic media/audio only. These tests do not prove perceived video quality.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import local_voices
import local_alignment
import narration_quality as nq
import render_video as rv
import video_pipeline as vp
import qa_engine

class Stage4AVQualityTests(unittest.TestCase):
    def wav(self,path:Path,duration=2.0):
        with wave.open(str(path),'wb') as w:
            w.setframerate(16000);w.setnchannels(1);w.setsampwidth(2)
            w.writeframes(b'\0'*int(16000*duration)*2)

    def test_18_voice_preference_only_installed_local_models(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name,quality in [('vi_VN-local-low','low'),('vi_VN-local-high','high'),
                                 ('en_US-local-medium','medium')]:
                (root/(name+'.onnx')).write_bytes(b'SYNTHETIC_MODEL_NOT_REAL')
                (root/(name+'.onnx.json')).write_text(json.dumps({'quality':quality}),encoding='utf-8')
            self.assertEqual(local_voices.choose(root,'vi-VN'),'vi_VN-local-high')
            self.assertEqual(local_voices.choose(root,'vi-VN','vi_VN-local-low'),'vi_VN-local-low')
            self.assertEqual(local_voices.choose(root,'en-US'),'en_US-local-medium')
            with self.assertRaisesRegex(ValueError,'not installed'):
                local_voices.choose(root,'vi-VN','vi_VN-not-present')
            self.assertTrue(all(v['voice_quality_not_audited'] for v in local_voices.available(root,'vi-VN')))

    def test_19_punctuation_pause_retains_approved_words(self):
        with tempfile.TemporaryDirectory() as t:
            w=Path(t)
            def fake(text,path,voice):
                self.wav(path,0.3)
            with patch.object(rv,'synth_piper',side_effect=fake):
                wav,cues,seconds=rv.build_audio(['A test sentence.','Another phrase'],w,'test','vi_VN-fixture',False)
            self.assertEqual([x[2] for x in cues],['A test sentence.','Another phrase'])
            self.assertGreater(cues[1][0]-cues[0][1],.2)
            self.assertLess(cues[1][0]-cues[0][1],.35)
            self.assertTrue(wav.is_file())
            self.assertGreater(seconds,cues[-1][1])

    def test_20_local_alignment_rejects_rewritten_text_and_invalid_times(self):
        with tempfile.TemporaryDirectory() as t:
            wav=Path(t)/'test.wav';self.wav(wav,2.0)
            cues=[{'start':0.1,'end':1.5,'text':'Tin moi'}]
            good={'schema':local_alignment.SCHEMA,'cues':[{'words':[
                {'text':'Tin','start':.12,'end':.6},
                {'text':'moi','start':.61,'end':1.3}]}]}
            aligned=local_alignment.validate(cues,good,wav)
            self.assertEqual(aligned[0]['words'][0]['alignment'],'LOCAL_OFFLINE_FORCED_ALIGNMENT_VALIDATED')
            self.assertEqual(aligned[0]['text'],'Tin moi')
            altered=json.loads(json.dumps(good));altered['cues'][0]['words'][1]['text']='fake'
            with self.assertRaisesRegex(ValueError,'changed'):
                local_alignment.validate(cues,altered,wav)
            altered=json.loads(json.dumps(good));altered['cues'][0]['words'][1]['end']=3.5
            with self.assertRaisesRegex(ValueError,'outside'):
                local_alignment.validate(cues,altered,wav)

    def test_20_optional_no_aligner_falls_back_and_never_claims_forced(self):
        with tempfile.TemporaryDirectory() as t:
            with patch.dict(os.environ,{'NEWS_LOCAL_ALIGNER':''}):
                aligned,status=local_alignment.run_if_configured([],Path(t)/'never.wav',Path(t),Path(t))
            self.assertIsNone(aligned)
            self.assertEqual(status,'CHUNK_REAL_WAV_WORD_ESTIMATED')

    def test_20_qa_alignment_claim_is_explicit_not_fabricated(self):
        with tempfile.TemporaryDirectory() as t:
            wav=Path(t)/'actual.wav';self.wav(wav,2.0)
            cue=[{'start':.1,'end':1.6,'text':'Synthetic only'}]
            base={'target_seconds':2,'stories':[{'narration':'Synthetic only'}]}
            estimated=nq.audit(cue,wav,base)
            measured=nq.audit(cue,wav,base,word_alignment='LOCAL_OFFLINE_FORCED_ALIGNMENT_VALIDATED')
            self.assertFalse(estimated['word_forced_alignment_performed'])
            self.assertTrue(measured['word_forced_alignment_performed'])
            self.assertEqual(measured['alignment'],'LOCAL_OFFLINE_FORCED_ALIGNMENT_VALIDATED')

    def test_21_music_filter_limits_peaks_and_ducks_bed(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            a=root/'silent_video.mp4';n=root/'narration.wav';m=root/'music.wav'
            for p in (a,n,m):p.write_bytes(b'SYNTHETIC')
            captures=[]
            with patch.object(vp,'execute',side_effect=lambda cmd,**kwargs:captures.append(cmd) or ''):
                vp.ffmpeg_master(a,n,root/'final.mp4','libx264',music=m)
                vp.ffmpeg_master(a,n,root/'plain.mp4','libx264')
            self.assertEqual(len(captures),2)
            self.assertIn('sidechaincompress',' '.join(map(str,captures[0])))
            self.assertIn('alimiter=limit=0.89',' '.join(map(str,captures[0])))
            self.assertIn('loudnorm',' '.join(map(str,captures[1])))
            self.assertIn('-shortest',captures[0])

    def test_22_smart_crop_manual_coordinates_wins(self):
        from scripts import smart_media
        expression=smart_media.crop_filter(1080,1920,{'focal_x':.8,'focal_y':.2})
        self.assertIn('crop=1080:1920',expression)
        self.assertIn('fps=30',expression)

    def test_23_media_rights_trace_present_even_without_smart_crop(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);src=base/'licensed.jpg';src.write_bytes(b'SYNTHETIC_IMAGE')
            scene={'type':'licensed_image','license_evidence':'TEST ONLY',
                   'media_path':'licensed.jpg','media_sha256':qa_engine.digest(src)}
            with patch.object(vp,'fit_image'):
                actual=vp.prepare_media({'visual_plan':[scene]},base,base,1,1080,1920,2,'t')
            self.assertEqual(actual['rights_trace']['source_sha256'],qa_engine.digest(src))
            self.assertTrue(actual['rights_trace']['human_scene_relevance_and_commercial_rights_review_required'])
            self.assertIn('author',actual['rights_trace']['metadata_incomplete'])

    def test_24_remotion_style_captions_and_shot_fades(self):
        jsx=(ROOT/'remotion-template'/'src'/'News.jsx').read_text(encoding='utf-8')
        self.assertIn('shotOpacity',jsx)
        self.assertIn('theme.accent',jsx)
        self.assertIn('subtitleBottom',jsx)
        self.assertIn('NewsVertical', (ROOT/'remotion-template'/'src'/'index.jsx').read_text())

    def test_25_private_remotion_site_per_job(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)
            template=base/'installed';src=template/'src';src.mkdir(parents=True)
            (src/'index.jsx').write_text('fixture',encoding='utf-8')
            (src/'News.jsx').write_text('fixture',encoding='utf-8')
            (template/'package.json').write_text('{}',encoding='utf-8')
            (template/'node_modules'/'remotion').mkdir(parents=True)
            j1=base/'job1';j2=base/'job2'
            (j1/'_work').mkdir(parents=True);(j2/'_work').mkdir(parents=True)
            if os.name=='nt':
                self.skipTest('Windows junction exercised by independent Windows acceptance')
            site1=vp.isolated_remotion_site(template,j1)
            site2=vp.isolated_remotion_site(template,j2)
            self.assertNotEqual(site1,site2)
            a=site1/'public'/'assets'/'private.jpg'
            a.write_bytes(b'ONE')
            self.assertFalse((site2/'public'/'assets'/'private.jpg').exists())
            self.assertFalse((template/'public'/'assets'/'private.jpg').exists())
            self.assertTrue((site1/'node_modules'/'remotion').is_dir())
            with self.assertRaises(FileExistsError):
                vp.isolated_remotion_site(template,j1)

if __name__=='__main__':
    unittest.main()
