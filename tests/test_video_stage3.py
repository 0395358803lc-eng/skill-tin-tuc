import copy, json, sys, tempfile, unittest, wave
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import video_pipeline as v
import render_video as legacy

class VideoStage3Tests(unittest.TestCase):
    def demo(self):
        return json.loads((ROOT/'examples'/'demo_brief.json').read_text(encoding='utf-8'))
    def test_aspects(self):
        self.assertEqual(v.FORMATS['9:16'][1:3],(1080,1920))
        self.assertEqual(v.FORMATS['16:9'][1:3],(1920,1080))
    def test_safe_paths_reject_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            with self.assertRaises(ValueError):v.secure_path(p,'../etc/data.png')
            with self.assertRaises(ValueError):v.secure_path(p,'C:/Windows/win.ini')
            with self.assertRaises(ValueError):v.secure_path(p,'not-present.png')
    def test_focal_crop_preserves_dimensions(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);src=root/'img.png';Image.new('RGB',(640,360),(14,44,88)).save(src)
            for w,h in ((1080,1920),(1920,1080)):
                out=root/('img'+str(w)+'.jpg');v.fit_image(src,out,w,h,.5,.5)
                with Image.open(out) as rendered:
                    self.assertEqual(rendered.size,(w,h))
            with self.assertRaises(ValueError):v.fit_image(src,root/'bad.jpg',640,360,1.7,.5)
    def test_requires_media_rights(self):
        item={'visual_plan':[{'type':'licensed_broll','media_path':'movie.mp4'}]}
        with self.assertRaisesRegex(ValueError,'rights evidence'):
            v.choose_media(item)
    def test_infographic_data_and_bounds(self):
        valid={'visual_plan':[{'type':'infographic','title':'Example only',
                              'data_points':[{'label':'A','value':60},{'label':'B','value':40}]}]}
        self.assertEqual(v.choose_media(valid)['kind'],'infographic')
        broken={'visual_plan':[{'type':'infographic','data_points':[{'label':'X','value':140}]}]}
        with self.assertRaisesRegex(ValueError,'data_points'):
            v.choose_media(broken)
    def test_card_default(self):
        self.assertIsNone(v.choose_media({'visual_plan':[{'type':'news_card'}]}))
    def test_gpu_cpu_fallback(self):
        self.assertEqual(v.select_encoder('cpu'),'libx264')
        with patch.object(legacy,'nvenc_available',return_value=False):
            self.assertEqual(v.select_encoder('auto'),'libx264')
            with self.assertRaisesRegex(RuntimeError,'NVENC'):
                v.select_encoder('nvenc')
    def test_approved_script_cannot_switch_aspect(self):
        sample=self.demo();sample['aspect_ratio']='both'
        legacy.validate_brief(sample,allow_demo=True)
        self.assertEqual(sample['aspect_ratio'],'both')
    def test_cue_offset_and_srt(self):
        self.assertEqual(legacy.stamp(1.5),'00:00:01,500')
        with tempfile.TemporaryDirectory() as directory:
            f=Path(directory)/'sub.srt'
            legacy.write_srt([(0.3,2.5,'A subtitle')],f)
            self.assertIn('00:00:00,300 --> 00:00:02,500',f.read_text(encoding='utf-8-sig'))

if __name__=='__main__':unittest.main()
