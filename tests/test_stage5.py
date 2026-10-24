"""Stage 14-15 regression: long DEMO fixtures, TTS cache, render-time profile."""
import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stage5_fixture as fixtures
import stage5_benchmark as bench
import render_video as legacy

class Stage5Tests(unittest.TestCase):
    def test_video_sizes_aspect_and_story_counts(self):
        for sec,stories in [(30,1),(60,3),(90,4),(180,5)]:
            for ratio in ('9:16','16:9','both'):
                b=fixtures.make(sec,'en-US',ratio)
                self.assertEqual(len(b['stories']),stories)
                self.assertEqual(b['aspect_ratio'],ratio)
                self.assertEqual(b['target_seconds'],sec)
                self.assertTrue(b['demo'])
                legacy.validate_brief(b,allow_demo=True)
    def test_vietnamese_long_scripts_are_marked_demo(self):
        for sec in (30,60,90,180):
            b=fixtures.make(sec,'vi-VN','both')
            self.assertTrue(b['demo'])
            self.assertTrue(all(s['approved'] for s in b['stories']))
            self.assertEqual(len(b['stories']),fixtures.COUNTS[sec])
            self.assertTrue(any('giả lập' in s['narration'] for s in b['stories']))
            with self.assertRaisesRegex(ValueError,'giả lập'):
                legacy.validate_brief(b,allow_demo=False)
    def test_piper_inprocess_keeps_one_loaded_model_across_chunks(self):
        import render_video
        class VoiceStub:
            loads=0
            def synthesize_wav(self,txt,dst,cfg):
                dst.setnchannels(1);dst.setframerate(22050);dst.setsampwidth(2)
                dst.writeframes(b'\x01\x00'*2000)
        class PiperVoiceStub:
            @staticmethod
            def load(path):
                VoiceStub.loads+=1
                return VoiceStub()
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            (folder/'stub.onnx').write_bytes(b'x')
            (folder/'stub.onnx.json').write_text('{}')
            with patch.dict(os.environ,{'PIPER_VOICE_DIR':td,
              'PIPER_BACKEND':'inprocess','PIPER_SPEECH_RATE':'1.0'}):
                with patch('piper.PiperVoice',PiperVoiceStub):
                    with patch.object(render_video,'_PIPER_VOICE_CACHE',{}):
                        render_video.synth_piper('First.',folder/'a.wav','stub')
                        render_video.synth_piper('Second.',folder/'b.wav','stub')
            self.assertEqual(VoiceStub.loads,1)
            with wave.open(str(folder/'b.wav'),'rb') as w:
                self.assertEqual(w.getframerate(),22050)
    def test_sampling_cannot_apply_to_real_approved_news(self):
        import video_pipeline
        with tempfile.TemporaryDirectory() as td:
            brief={'demo':False}
            with self.assertRaisesRegex(ValueError,'forbidden'):
                video_pipeline.render(brief,Path(td)/'brief.json',Path(td)/'out',
                    '9:16','en_US-lessac-medium','cpu',sample_every=5)
    def test_demo_fixture_source_urls_are_not_factual(self):
        for length in (30,60,90,180):
            b=fixtures.make(length,'en-US','9:16')
            for story in b['stories']:
                self.assertTrue(story['sources'][0]['url'].startswith('https://example.com/'))
    def test_benchmark_forwards_speech_rate_to_pipeline_command(self):
        import stage5_benchmark
        cmd=stage5_benchmark.pipeline_argv(Path('input.json'),Path('output'),'auto',1,.86)
        self.assertEqual(cmd[cmd.index('--speech-rate')+1],'0.86')
        self.assertEqual(cmd[cmd.index('--demo-sample-every')+1],'1')
    def test_preview_samples_each_story_not_only_global_percentage(self):
        import qa_engine
        with tempfile.TemporaryDirectory() as td:
            props=Path(td)/'props.json'
            props.write_text(json.dumps({'stories':[
                {'durationFrames':300},{'durationFrames':300},
                {'durationFrames':300},{'durationFrames':300}]}),encoding='utf-8')
            times=qa_engine.preview_points(40.,props)
            self.assertGreaterEqual(len(times),5)
            midpoints=[s for label,s in times if label.startswith('story_')]
            self.assertGreaterEqual(len(midpoints),3)
            self.assertTrue(any(abs(t-25)<.1 for t in midpoints))
    def test_perf_benchmark_requires_demo_and_unique_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            brief=root/'fake.json'
            b=fixtures.make(30,'en-US','9:16')
            b['demo']=False
            brief.write_text(json.dumps(b))
            with self.assertRaisesRegex(ValueError,'refuses real news'):
                bench.measure(brief,root/'out', 'auto',root/'metrics')
            b['demo']=True
            brief.write_text(json.dumps(b))
            (root/'out').mkdir()
            with self.assertRaisesRegex(ValueError,'already exists'):
                bench.measure(brief,root/'out','auto',root/'metrics')
if __name__=='__main__':
    unittest.main()

class Stage5FFmpegResolutionTests(unittest.TestCase):
    def test_qa_uses_explicit_windows_ffprobe_executable(self):
        import qa_engine as q
        runtime=Path(os.environ.get('NEWS_SKILL_RUNTIME',str(ROOT.parent/(ROOT.name+'-runtime'))))
        expected=runtime/'tools'/'ffmpeg-selected'/'ffprobe.exe'
        if not expected.is_file():
            self.skipTest('Portable test: local FFprobe binary is not installed')
        with patch.object(q.subprocess,'run') as mocked:
            mocked.return_value.returncode=0
            mocked.return_value.stdout="ffprobe built"
            self.assertEqual(q.command(['ffprobe','-version']),'ffprobe built')
            self.assertEqual(Path(mocked.call_args[0][0][0]).resolve(),expected.resolve())
