"""Stage 18/19 validation: real local WAV timing, Smart Crop and 2 aspect profiles."""
import copy,hashlib,json,math,os,subprocess,sys,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import narration_quality as nq
import smart_media as sm
import video_pipeline as vp
import qa_engine as qa

class Stage18VoiceTests(unittest.TestCase):
    def make_wav(self,path,seconds=3,rate=22050):
        with wave.open(str(path),'wb') as o:
            o.setframerate(rate);o.setsampwidth(2);o.setnchannels(1)
            o.writeframes(b'\0\0'*int(rate*seconds))
    def test_word_timing_monotonic_ends_at_measured_cue(self):
        cue={'start':.3,'end':2.9,'text':'AI đã công bố thông tin mới.'}
        words=nq.word_timing(cue)
        self.assertEqual([x['text'] for x in words],cue['text'].split())
        self.assertEqual(words[0]['start'],.3)
        self.assertEqual(words[-1]['end'],2.9)
        self.assertTrue(all(a['end']<=b['start']+.001 for a,b in zip(words,words[1:])))
        self.assertTrue(all(x['alignment']=='ESTIMATED_WITHIN_PIPER_CHUNK' for x in words))
    def test_lexicon_only_changes_tts_and_requires_review(self):
        lex=nq.lexicon_review('AI phát triển AI.',{'AI':'ây-ai','NASA':'na-sa'})
        self.assertEqual(lex['matched'][0]['occurrences'],2)
        self.assertTrue(lex['subtitle_uses_original_wording'])
        with self.assertRaises(ValueError):nq.lexicon_review('Text',{'':'invalid'})
    def test_real_wav_duration_and_warning(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);audio=folder/'narration.wav';self.make_wav(audio,3)
            brief={'target_seconds':3,'stories':[{'narration':'Sự kiện năm 2026.'}]}
            cues=[{'start':.3,'end':1.1,'text':'Sự kiện'},
                  {'start':1.35,'end':2.9,'text':'năm 2026.'}]
            result=nq.save_audit(cues,audio,brief,folder/'voice.json')
            self.assertAlmostEqual(result['voice_real_wav_seconds'],3.,places=2)
            self.assertFalse(result['word_forced_alignment_performed'])
            self.assertIn('NUMBERS_AND_DATES_NEED_HUMAN_PRONUNCIATION_REVIEW',result['warnings'])
            with self.assertRaises(FileExistsError):nq.save_audit(cues,audio,brief,folder/'voice.json')
    def test_misaligned_cues_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'speech.wav';self.make_wav(p,1)
            with self.assertRaises(ValueError):
                nq.audit([{'start':.3,'end':3.,'text':'too late'}],p,
                  {'target_seconds':1,'stories':[{'narration':'too late'}]})
    def test_remotion_has_word_highlight_and_safe_caption(self):
        js=(ROOT/'remotion-template'/'src'/'News.jsx').read_text(encoding='utf-8')
        self.assertIn('active.words',js)
        self.assertIn('subtitleBottom',js)
        self.assertIn('p.subtitleBottom',js)
        self.assertIn('#64D9FF',js)

class Stage19SmartMediaTests(unittest.TestCase):
    def test_image_focus_and_static_export_two_ratios(self):
        from PIL import Image,ImageDraw
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);im=Image.new('RGB',(900,600),(20,26,34))
            dr=ImageDraw.Draw(im)
            for x in range(620,850,11):
                for y in range(190,500,13):
                    dr.ellipse((x,y,x+6,y+6),fill=(250,240,40))
            src=root/'approved_media.png';im.save(src)
            h=qa.digest(src)
            scene={'type':'licensed_image','media_path':src.name,'media_sha256':h,
              'license_evidence':'Synthetic media created for automated test',
              'smart_crop':True,'source_url':'local-fixture','author':'Automation test',
              'license_name':'Test fixture owned','attribution':'Test only'}
            focus=sm.image_focus(src)
            self.assertTrue(0<=focus['focal_x']<=1)
            self.assertTrue(0<=focus['focal_y']<=1)
            for width,height in ((1080,1920),(1920,1080)):
                work=root/(str(width));work.mkdir()
                out=vp.prepare_media({'visual_plan':[scene]},root,work,1,width,height,1)
                self.assertEqual(out['kind'],'image')
                self.assertTrue(out['rights_trace']['human_commercial_rights_check_still_required'])
                with Image.open(work/out['asset']) as processed:
                    self.assertEqual(processed.size,(width,height))
            self.assertEqual(qa.digest(src),h)
    def test_manual_focal_override_wins(self):
        case={'visual_plan':[{'type':'licensed_image','license_evidence':'TEST',
            'media_path':'ok.jpg','media_sha256':'0'*64,'focal_x':.9,'focal_y':.1,'smart_crop':True}]}
        choice=vp.choose_media(case)
        self.assertTrue(choice['manual_focus'])
        self.assertEqual(choice['focal_x'],.9)
        self.assertTrue(choice['smart_crop'])
    def test_smart_crop_hash_and_rights_required(self):
        with tempfile.TemporaryDirectory() as t:
            from PIL import Image
            root=Path(t);src=root/'x.png'
            Image.new('RGB',(640,360),(10,20,30)).save(src)
            out=root/'work';out.mkdir()
            case={'visual_plan':[{'type':'licensed_image','media_path':'x.png',
                    'license_evidence':'Synthetic','smart_crop':True}]}
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                vp.prepare_media(case,root,out,1,1080,1920,1)
            case['visual_plan'][0]['media_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                vp.prepare_media(case,root,out,1,1080,1920,1)
    def test_dynamic_expression_and_ffmpeg_export(self):
        cv2=sm._opencv()
        if cv2 is None:self.skipTest('OpenCV optional package not installed')
        import numpy as np
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);path=root/'synthetic.mp4'
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),12,(320,240))
            if not writer.isOpened():self.skipTest('MP4V encoder not supported')
            for i in range(36):
                image=np.zeros((240,320,3),dtype=np.uint8)
                image[:]=(20,25,30)
                x=30+i*4
                image[80:145,x:x+55]=(245,235,45)
                writer.write(image)
            writer.release()
            result=sm.video_focus(path,3,samples=5)
            self.assertEqual(result['samples'],5)
            self.assertTrue(all(0<=p['fx']<=1 for p in result['track']))
            filt=sm.crop_filter(360,640,result)
            ff=Path(os.environ.get('NEWS_SKILL_RUNTIME',
               str(ROOT.parent/(ROOT.name+'-runtime'))))/'tools'/'ffmpeg-selected'/'ffmpeg.exe'
            if not ff.is_file():self.skipTest('FFmpeg not installed on this host')
            out=root/'crop.mp4'
            cmd=[str(ff),'-hide_banner','-loglevel','error','-i',str(path),
                 '-t','1','-vf',filt,'-an','-c:v','libx264','-preset','ultrafast',
                 '-pix_fmt','yuv420p',str(out)]
            z=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=90)
            self.assertEqual(z.returncode,0,z.stderr[-1200:])
            self.assertTrue(out.is_file() and out.stat().st_size>1000)
    def test_invalid_track_rejected(self):
        with self.assertRaises(ValueError):
            sm.linear_track_expr([{'t':2,'fx':.4},{'t':1,'fx':.5}],'fx')
        with self.assertRaises(ValueError):
            sm.linear_track_expr([{'t':1,'fx':3}],'fx')

if __name__=='__main__':unittest.main()
