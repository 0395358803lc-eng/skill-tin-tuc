import importlib.util
import json
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('render_video', ROOT/'scripts'/'render_video.py')
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
class SkillTests(unittest.TestCase):
    def setUp(self):
        self.demo=json.loads((ROOT/'examples'/'demo_brief.json').read_text(encoding='utf-8'))
    def test_demo_blocked_by_default(self):
        with self.assertRaisesRegex(ValueError,'dữ liệu giả lập'):
            mod.validate_brief(self.demo)
    def test_demo_permitted_explicitly(self):
        mod.validate_brief(self.demo, allow_demo=True)
    def test_real_video_requires_approval(self):
        self.demo['demo']=False; self.demo['status']='draft'
        with self.assertRaisesRegex(ValueError,'approved'):
            mod.validate_brief(self.demo)
    def test_source_independence(self):
        self.demo['stories'][0]['sources'][1]['url']='https://www.example.com/other'
        with self.assertRaisesRegex(ValueError,'nguồn độc lập'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_caption_segments(self):
        items=mod.chunks('Xin chào các bạn. Đây là bản tin thử nghiệm hôm nay!')
        self.assertEqual(len(items),2)
        self.assertEqual(mod.stamp(1.375),'00:00:01,375')
    def test_photo_license(self):
        self.demo['stories'][0]['image_path']='photo.jpg'
        with self.assertRaisesRegex(ValueError,'image_license'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_timestamp_timezone_required(self):
        self.demo['as_of'] = '2026-10-23T21:00:00'
        with self.assertRaisesRegex(ValueError, 'múi giờ'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_reject_insecure_image_path(self):
        self.demo['stories'][0]['image_path'] = '../private.jpg'
        self.demo['stories'][0]['image_license'] = 'own'
        with self.assertRaisesRegex(ValueError, 'image_path'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_reject_unapproved_story(self):
        self.demo['demo'] = False
        self.demo['stories'][0]['approved'] = False
        with self.assertRaisesRegex(ValueError, 'chưa được người dùng duyệt'):
            mod.validate_brief(self.demo)
    def test_reject_invalid_url(self):
        self.demo['stories'][0]['sources'][1]['url'] = 'file:///private.txt'
        with self.assertRaisesRegex(ValueError, 'http'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_reject_oversized_narration(self):
        self.demo['stories'][0]['narration'] = 'a' * 4001
        with self.assertRaisesRegex(ValueError, 'quá mức'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_reject_null_narration(self):
        self.demo['stories'][0]['narration'] = None
        with self.assertRaisesRegex(ValueError, 'narration'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_reject_boolean_duration(self):
        self.demo['target_seconds'] = True
        with self.assertRaisesRegex(ValueError, 'target_seconds'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_reject_malformed_sources(self):
        self.demo['stories'][0]['sources'][1] = {'url': None}
        with self.assertRaisesRegex(ValueError, 'URL dạng chuỗi'):
            mod.validate_brief(self.demo, allow_demo=True)
    def test_duration_status_and_override(self):
        self.assertEqual(mod.duration_status(64.9, 60), 'PASS')
        self.assertEqual(mod.duration_status(72.0, 60), 'NEEDS_EDITORIAL_TRIM')
        self.assertEqual(mod.duration_status(72.0, 60, True), 'PASS_LONGER_ACCEPTED')
    def test_media_probe_reject_missing_audio(self):
        original = mod.run
        try:
            mod.run = lambda *args, **kwargs: '{"streams":[{"codec_type":"video","width":1080,"height":1920,"codec_name":"h264"}]}'
            with self.assertRaisesRegex(RuntimeError, 'luồng âm thanh'):
                mod.verify_media(ROOT / 'not-real.mp4')
        finally:
            mod.run = original
if __name__=='__main__': unittest.main()
