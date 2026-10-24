"""Stage 20: preset identities, approved style hash, safe areas and source-only media."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import studio_design as studio
import editorial_core as core
from test_editorial import bundle,script,NOW

class Stage20ThemeTests(unittest.TestCase):
    def brief(self,language='vi-VN',style='roundup'):
        narration=('This is a synthetic studio test, not factual reporting.'
             if language.startswith('en') else
             'Đây là nội dung kiểm thử giả lập, không phản ánh tin tức thật.')
        return {'country':'US','category':'technology','language':language,
                'visual_style':style,'target_seconds':30,'aspect_ratio':'both',
                'stories':[{'headline':'Testing a deliberately long Unicode headline tiếng Việt: \u1ee8ng d\u1ee5ng AI trong ph\u00f2ng tin',
                  'summary':'A synthetic summary with date 24/10/2026. Nothing factual is being reported.',
                  'narration':narration,'visual_plan':[{'type':'news_card'}]}]}
    def test_three_presets_have_distinct_palette_and_pacing(self):
        styles=studio.PRESETS
        self.assertEqual(set(styles),{'quick','roundup','deep_dive'})
        self.assertEqual(len({s['colors']['accent'] for s in styles.values()}),3)
        self.assertEqual(len({s['transition_frames'] for s in styles.values()}),3)
        for v in styles.values():
            for key in ('intro_frames','outro_frames','transition_frames'):
                self.assertTrue(1<=v[key]<=18)
    def test_all_profiles_preserve_language_and_user_copy(self):
        for lang in ('vi-VN','en-US'):
            for name in studio.PRESETS:
                b=self.brief(lang,name)
                before=json.dumps(b,ensure_ascii=False,sort_keys=True)
                result=studio.validate(b)
                self.assertEqual(result['visual_style'],name)
                self.assertEqual(result['language'],lang)
                self.assertEqual(json.dumps(b,ensure_ascii=False,sort_keys=True),before)
                self.assertFalse(result['identity_assets_external'])
                self.assertTrue(result['human_visual_review_required'])
    def test_legacy_style_default_is_roundup(self):
        b=self.brief();b.pop('visual_style')
        self.assertEqual(studio.validate(b)['visual_style'],'roundup')
    def test_invalid_style_and_language_rejected(self):
        b=self.brief();b['visual_style']='CUSTOM_UNKNOWN'
        with self.assertRaises(ValueError):studio.validate(b)
        b=self.brief();b['language']='ja-JP'
        with self.assertRaises(ValueError):studio.validate(b)
    def test_content_not_silently_truncated(self):
        b=self.brief()
        b['stories'][0]['headline']='X'*236
        with self.assertRaisesRegex(ValueError,'too long'):
            studio.validate(b)
        b=self.brief()
        b['stories'][0]['summary']='Y'*461
        with self.assertRaisesRegex(ValueError,'too long'):
            studio.validate(b)
    def test_long_copy_generates_review_warning(self):
        b=self.brief()
        b['stories'][0]['headline']='Vietnamese tiếng Việt '+'AI News '*14
        b['stories'][0]['summary']='Tóm tắt '*38
        warnings=studio.validate(b)['warnings']
        self.assertTrue(any(x['code']=='LONG_HEADLINE_NEEDS_VISUAL_QA' for x in warnings))
        self.assertTrue(any(x['code']=='LONG_SUMMARY_NEEDS_VISUAL_QA' for x in warnings))
    def test_infographic_requires_compact_copy_and_noninvented_numbers(self):
        b=self.brief()
        b['stories'][0]['visual_plan']=[{'type':'infographic',
            'data_points':[{'label':'Synthetic metric','value':60}]}]
        self.assertTrue(studio.validate(b))
        b['stories'][0]['headline']='X'*200
        with self.assertRaisesRegex(ValueError,'shorter approved'):
            studio.validate(b)
        b=self.brief()
        b['stories'][0]['visual_plan']=[{'type':'infographic',
            'data_points':[{'label':'Fake','value':110}]}]
        with self.assertRaisesRegex(ValueError,'0..100'):
            studio.validate(b)
    def test_safe_area_no_vertical_caption_infographic_overlap(self):
        a=studio.SAFE_AREAS['9:16']
        # Values are backed by the fixed React profile (Stage20).
        chart_top=940;chart_max_height=375
        caption_top=a['height']-a['subtitle_bottom']-192
        self.assertLessEqual(chart_top+chart_max_height,caption_top)
        self.assertGreater(a['subtitle_bottom'],300)
        self.assertGreater(a['right_guard'],100)
        b=studio.SAFE_AREAS['16:9']
        self.assertLessEqual(242+470,b['height']-b['subtitle_bottom']-130)
    def test_design_preflight_create_only(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'visual_design.json'
            report=studio.save_preflight(self.brief(),p)
            self.assertEqual(json.loads(p.read_text())['visual_style'],'roundup')
            with self.assertRaises(FileExistsError):
                studio.save_preflight(self.brief(),p)
    def test_render_props_cannot_override_approved_theme(self):
        b=self.brief(style='deep_dive')
        props=studio.render_props(b)
        self.assertEqual(props['visual_style'],'deep_dive')
        self.assertNotIn('narration',props)
        self.assertNotIn('stories',props)
    def test_scene_metadata_brand_is_original_vectors(self):
        self.assertEqual(studio.BRAND['mark'],'AN')
        self.assertIn('Original',studio.BRAND['copyright_free'])
    def test_remotion_has_safe_caption_and_intro_outro(self):
        jsx=(ROOT/'remotion-template'/'src'/'News.jsx').read_text(encoding='utf-8')
        for key in ('styleId','isFirst','isLast','introFrames','outroFrames','transitionFrames',
                    'subtitleBottom','sourceBottom','DEMO','Infographic','OffthreadVideo',
                    'Story','Caption','fontSize','objectFit'):
            self.assertIn(key,jsx)
        self.assertNotIn('t(story.headline',jsx)
        self.assertNotIn('t(story.summary',jsx)
        self.assertNotIn('WebkitLineClamp',jsx)
        self.assertIn('chartHeadlineSize',jsx)
        self.assertIn('chartSummarySize',jsx)
        self.assertIn('useRightChart?300',jsx)
        self.assertNotIn('\ufffd',jsx)
    def test_approved_editorial_hash_changes_with_visual_style(self):
        data=bundle()
        selected=core.choose(data,core.check_bundle(data),['EVENT-01'],'Unit test user chose story',NOW)
        base=script()
        base['visual_style']='quick'
        quick=core.draft_manifest(data,selected,base)
        altered=copy.deepcopy(base);altered['visual_style']='deep_dive'
        deep=core.draft_manifest(data,selected,altered)
        self.assertNotEqual(core.canonical_hash(quick),core.canonical_hash(deep))
        confirmation={'confirmed_at':NOW,'user_confirmation':'Unit test only',
                      'script_sha256':core.canonical_hash(quick),
                      'approved_story_ids':['EVENT-01']}
        with self.assertRaises(ValueError):
            core.approve_draft(deep,confirmation)
    def test_long_summary_in_english_and_vietnamese_is_valid_when_safe(self):
        for lang in ('en-US','vi-VN'):
            b=self.brief(lang)
            b['stories'][0]['summary']='Report demo only. '*12
            self.assertTrue(studio.validate(b))
    def test_python_preset_palette_matches_remotion_css(self):
        jsx=(ROOT/'remotion-template'/'src'/'News.jsx').read_text(encoding='utf-8')
        for style,profile in studio.PRESETS.items():
            self.assertIn(style,jsx)
            for color in profile['colors'].values():
                self.assertIn(color,jsx)

    def test_no_tiktok_or_youtube_upload_integrated(self):
        jsx=(ROOT/'remotion-template'/'src'/'News.jsx').read_text(encoding='utf-8')
        self.assertNotIn('tiktok.com',jsx.lower())
        self.assertNotIn('youtube.com',jsx.lower())

if __name__=='__main__':unittest.main()
