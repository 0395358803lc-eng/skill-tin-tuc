import json,sys,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import tts_duration_preflight as p

class PreflightTests(unittest.TestCase):
    def config(self):
        return {'language':'vi-VN','target_seconds':60,'stories':[{'narration':'Đây là lời dẫn thử nghiệm tiếng Việt không phải sự kiện thực tế.'}]}
    def test_refuses_approved_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'approved.json'
            source.write_text(json.dumps(self.config()),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'BEFORE approval'):
                p.preflight(source,Path(d)/'out')
    def test_refuses_explicit_approved_status(self):
        with tempfile.TemporaryDirectory() as d:
            inp=self.config();inp['status']='approved'
            path=Path(d)/'candidate.json';path.write_text(json.dumps(inp))
            with self.assertRaisesRegex(ValueError,'approved'):
                p.preflight(path,Path(d)/'out')
    def test_rejects_invalid_speech_rate(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'candidate.json';f.write_text(json.dumps(self.config()))
            with self.assertRaisesRegex(ValueError,'rate'):
                p.preflight(f,Path(d)/'out',speech_rate=1.7)
    def test_audio_duration_reports_without_changing_input(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'candidate.json';f.write_text(json.dumps(self.config()))
            before=f.read_bytes()
            def stub_audio(obj,folder,voice,silence):
                path=folder/'narration.wav'
                with wave.open(str(path),'wb') as w:
                    w.setnchannels(1);w.setframerate(1000);w.setsampwidth(2)
                    w.writeframes(b'\x01\x00'*60000)
                return path,[{}],[1,2,3],1800
            with patch.object(p.pipe,'audio_track',side_effect=stub_audio):
                result=p.preflight(f,Path(d)/'out')
            self.assertEqual(before,f.read_bytes())
            self.assertTrue(result['within_five_percent'])
            self.assertEqual(result['measured_seconds'],60.)
            self.assertTrue(Path(d,'out','duration_preflight.json').exists())
            with self.assertRaisesRegex(ValueError,'already exists'):
                p.preflight(f,Path(d)/'out')
if __name__=='__main__':unittest.main()
