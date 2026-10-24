"""Stage 15 production-safe regression tests: time, stability, GPU fallback, no overwrite."""
import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stage15_duration_calibrate as duration
import stage15_stability as stability
import stage5_fixture as fixture
import stage5_benchmark as bench
import video_pipeline as pipeline

class DurationCalibrationTests(unittest.TestCase):
    def test_resize_demo_only_and_no_mutation(self):
        base=fixture.make(60,'vi-VN','both')
        before=json.dumps(base,ensure_ascii=False,sort_keys=True)
        new=duration.resize(base,250)
        self.assertEqual(sum(len(x['narration'].split()) for x in new['stories']),250)
        self.assertEqual(json.dumps(base,ensure_ascii=False,sort_keys=True),before)
        self.assertTrue(new['demo'])
        self.assertEqual(len(new['stories']),3)
        self.assertEqual(new['aspect_ratio'],'both')
    def test_calibration_never_resizes_real_news(self):
        news=fixture.make(60,'vi-VN','both')
        news['demo']=False
        with self.assertRaisesRegex(ValueError,'real approved'):
            duration.resize(news,240)
    def test_bounded_calibration_converges_without_rendering_video(self):
        with tempfile.TemporaryDirectory() as td:
            def simulated_audio(brief,probe_root):
                current=duration.tokens(brief['stories'])
                return {'seconds':round(current/2.5,3),'tokens':current,
                    'video_seconds':round(current/2.5,3),'caption_cues':2,
                    'story_count':1,'tts_elapsed_s':.01}
            with patch.object(duration,'actual_audio',side_effect=simulated_audio):
                obj=duration.calibrate(30,'en-US',Path(td)/'calibration',max_attempts=3)
            self.assertTrue(obj['within_five_percent'])
            self.assertLessEqual(len(obj['trials']),3)
            self.assertTrue(Path(obj['manifest']).is_file())
            self.assertTrue(json.loads(Path(obj['manifest']).read_text())['demo'])
    def test_refuses_overwriting_preexisting_calibration(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'output exists'):
                duration.calibrate(30,'en-US',Path(td),max_attempts=1)
    def test_unknown_profile_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                duration.calibrate(24,'en-US',Path(td)/'bad')

class StabilityContracts(unittest.TestCase):
    def test_pipeline_argv_forwards_rate_and_never_uses_sampling_for_native(self):
        argv=bench.pipeline_argv(Path('demo.json'),Path('newout'),'auto',1,1.12)
        self.assertEqual(argv[argv.index('--demo-sample-every')+1],'1')
        self.assertEqual(argv[argv.index('--speech-rate')+1],'1.12')
    def test_fallback_to_cpu_encoder_when_nvenc_is_unavailable(self):
        with patch.object(pipeline.legacy,'nvenc_available',return_value=False):
            self.assertEqual(pipeline.select_encoder('auto'),'libx264')
            self.assertEqual(pipeline.select_encoder('cpu'),'libx264')
            with self.assertRaisesRegex(RuntimeError,'NVENC'):
                pipeline.select_encoder('nvenc')
    def test_nvenc_can_be_used_when_operational(self):
        with patch.object(pipeline.legacy,'nvenc_available',return_value=True):
            self.assertEqual(pipeline.select_encoder('auto'),'h264_nvenc')
    def test_benchmark_refuses_real_news(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'approved.json'
            f.write_text(json.dumps({'demo':False}))
            with self.assertRaisesRegex(ValueError,'real news'):
                bench.measure(f,Path(td)/'out','auto',Path(td)/'report')
    def test_snapshot_is_read_only_and_not_an_approval(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'data'
            p.write_bytes(b'SAFE')
            before=p.stat().st_mtime_ns
            obj=stability.snapshot([p])
            self.assertEqual(obj[str(p)],stability.qa.digest(p))
            self.assertEqual(p.stat().st_mtime_ns,before)
    def test_render_guards_sampling_for_real_news(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'forbidden'):
                pipeline.render({'demo':False},Path(td)/'approved.json',Path(td)/'out',
                    '9:16','vi_VN-vais1000-medium','auto',sample_every=10)
class BenchmarkWatchdogTests(unittest.TestCase):
    def test_terminates_only_benchmark_owned_process_tree(self):
        import types
        events=[]
        class Child:
            def __init__(self,n):self.name=n
            def terminate(self):events.append('term:'+self.name)
        class Process:
            def terminate(self):events.append('parent_term')
            def wait(self,timeout):events.append('parent_wait')
        class App:
            def children(self,recursive):return [Child('one'),Child('two')]
        fake=types.SimpleNamespace(NoSuchProcess=LookupError,AccessDenied=PermissionError,
            wait_procs=lambda children,timeout:(children,[]))
        bench.stop_benchmark_process_tree(Process(),App(),fake)
        self.assertEqual(events,['term:two','term:one','parent_term','parent_wait'])

if __name__=='__main__':unittest.main()
