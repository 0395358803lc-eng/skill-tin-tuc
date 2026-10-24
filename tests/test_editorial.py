import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import editorial_core as core
import news_rss as rss
import news_editor as editor
import source_reader as reader

NOW = '2026-10-23T18:00:00Z'

def bundle():
    return {'as_of': NOW, 'stories': [{
        'id': 'EVENT-01', 'headline': 'Fictional proof-of-concept event',
        'summary': 'This is a unit-test fixture, NOT actual news.',
        'event_country': 'US', 'event_at': '2026-10-23T12:00:00Z',
        'category': 'science', 'confidence': 'high',
        'confidence_rationale': 'Unit-test fixture with two independent evidence records.',
        'contradictions_unresolved': False, 'impact_score': 3, 'video_fit_score': 4,
        'sources': [
            {'id': 'SRC-A', 'url': 'https://example.com/sample-a', 'publisher': 'Publisher A',
             'origin_id': 'org-a', 'source_type': 'primary', 'read_confirmed': True,
             'published_at': NOW, 'retrieved_at': NOW, 'evidence_note': 'Sample direct evidence recorded for the test.'},
            {'id': 'SRC-B', 'url': 'https://example.org/sample-b', 'publisher': 'Publisher B',
             'origin_id': 'org-b', 'source_type': 'secondary', 'read_confirmed': True,
             'published_at': NOW, 'retrieved_at': NOW, 'evidence_note': 'Another independent evidence note for the test.'}
        ],
        'claims': [{'id': 'C1', 'text': 'A fictional event occurred', 'source_ids': ['SRC-A', 'SRC-B']}]
    }]}

def script():
    return {'project_name': 'test-only', 'country': 'US', 'category': 'science',
            'language': 'vi-VN', 'aspect_ratio': 'both', 'target_seconds': 60,
            'video_title': 'Unit test only', 'hashtags': ['#test'],
            'stories': [{'id': 'EVENT-01', 'headline': 'Fictional unit test',
                         'summary': 'Only a unit test, not real news',
                         'narration': 'This is a unit test; this event is fictional.',
                         'claim_ids': ['C1']}]}

class EditorialTests(unittest.TestCase):
    def test_two_independent_evidenced_sources(self):
        report = core.check_bundle(bundle())
        self.assertEqual(report['eligible_count'], 1)
        self.assertFalse(report['story_reports'][0]['factually_verified_by_software'])

    def test_same_organization_rejected(self):
        b = bundle()
        b['stories'][0]['sources'][1]['origin_id'] = 'org-a'
        self.assertEqual(core.check_bundle(b)['eligible_count'], 0)

    def test_same_website_rejected(self):
        b = bundle()
        b['stories'][0]['sources'][1]['url'] = 'https://news.example.com/other'
        self.assertEqual(core.check_bundle(b)['eligible_count'], 0)

    def test_syndicated_copy_rejected(self):
        b = bundle()
        b['stories'][0]['sources'][1]['syndicated_copy'] = True
        self.assertEqual(core.check_bundle(b)['eligible_count'], 0)

    def test_unread_article_rejected(self):
        b = bundle()
        b['stories'][0]['sources'][1]['read_confirmed'] = False
        self.assertEqual(core.check_bundle(b)['eligible_count'], 0)

    def test_unresolved_contradictions_rejected(self):
        b = bundle()
        b['stories'][0]['contradictions_unresolved'] = True
        self.assertEqual(core.check_bundle(b)['eligible_count'], 0)

    def test_high_claim_requires_two_sources(self):
        b = bundle()
        b['stories'][0]['claims'][0]['source_ids'] = ['SRC-A']
        self.assertEqual(core.check_bundle(b)['eligible_count'], 0)

    def test_low_confidence_not_eligible(self):
        b = bundle()
        b['stories'][0]['confidence'] = 'low'
        self.assertEqual(core.check_bundle(b)['eligible_count'], 0)

    def test_missing_timezone_rejected(self):
        b = bundle()
        b['stories'][0]['event_at'] = '2026-10-23T12:00:00'
        self.assertEqual(core.check_bundle(b)['eligible_count'], 0)

    def test_demo_cannot_enter_selection(self):
        b = bundle()
        b['demo'] = True
        report = core.check_bundle(b)
        self.assertEqual(report['eligible_count'], 0)
        with self.assertRaisesRegex(ValueError, 'DEMO'):
            core.choose(b, report, ['EVENT-01'], 'Select', NOW)

    def test_selection_requires_user_message(self):
        b = bundle()
        with self.assertRaisesRegex(ValueError, 'explicit user'):
            core.choose(b, core.check_bundle(b), ['EVENT-01'], '', NOW)

    def test_selection_rejects_unknown_id(self):
        b = bundle()
        with self.assertRaisesRegex(ValueError, 'unknown'):
            core.choose(b, core.check_bundle(b), ['EVENT-99'], 'I choose', NOW)

    def test_valid_selection_then_draft(self):
        b = bundle()
        selection = core.choose(b, core.check_bundle(b), ['EVENT-01'], 'I choose EVENT-01', NOW)
        d = core.draft_manifest(b, selection, script())
        self.assertEqual(d['status'], 'draft')
        self.assertFalse(d['stories'][0]['approved'])
        self.assertEqual(d['aspect_ratio'], 'both')
        self.assertEqual(d['stories'][0]['claim_ids'], ['C1'])

    def test_script_must_cite_claim_ids(self):
        b = bundle()
        sel = core.choose(b, core.check_bundle(b), ['EVENT-01'], 'Choose it', NOW)
        sc = script()
        sc['stories'][0]['claim_ids'] = ['NONEXISTENT']
        with self.assertRaisesRegex(ValueError, 'claim_ids'):
            core.draft_manifest(b, sel, sc)

    def test_approval_requires_exact_hash(self):
        b = bundle()
        sel = core.choose(b, core.check_bundle(b), ['EVENT-01'], 'Choose it', NOW)
        draft = core.draft_manifest(b, sel, script())
        conf = {'confirmed_at': NOW, 'user_confirmation': 'Approve reviewed script',
                'approved_story_ids': ['EVENT-01'], 'script_sha256': 'wrong'}
        with self.assertRaisesRegex(ValueError, 'changed'):
            core.approve_draft(draft, conf)
        conf['script_sha256'] = core.canonical_hash(draft)
        signed = core.approve_draft(draft, conf)
        self.assertTrue(signed['stories'][0]['approved'])
        self.assertEqual(signed['status'], 'approved')
        self.assertFalse(draft['stories'][0]['approved'])

    def test_storyboard_fallback_and_media_license_gate(self):
        b = bundle()
        s = core.choose(b, core.check_bundle(b), ['EVENT-01'], 'Choose fixture', NOW)
        draft = core.draft_manifest(b, s, script())
        self.assertEqual(draft['stories'][0]['visual_plan'][0]['type'], 'news_card')
        broken = script()
        broken['stories'][0]['visual_plan'] = [{
            'type': 'licensed_broll', 'instruction': 'Use real media',
            'claim_ids': ['C1']
        }]
        with self.assertRaisesRegex(ValueError, 'rights evidence'):
            core.draft_manifest(b, s, broken)

    def test_real_render_approval_hash_and_aspect_gate(self):
        import render_video
        b = bundle()
        selection = core.choose(b, core.check_bundle(b), ['EVENT-01'], 'Choose sample', NOW)
        sc = script()
        sc['aspect_ratio'] = '9:16'
        draft = core.draft_manifest(b, selection, sc)
        with self.assertRaisesRegex(ValueError, 'approved'):
            render_video.validate_brief(draft)
        conf = {'confirmed_at': NOW, 'user_confirmation': 'I approve exact sample text',
                'approved_story_ids': ['EVENT-01'], 'script_sha256': core.canonical_hash(draft)}
        approved = core.approve_draft(draft, conf)
        render_video.validate_brief(approved)
        modified = copy.deepcopy(approved)
        modified['stories'][0]['narration'] += ' Something else.'
        with self.assertRaisesRegex(ValueError, 'thay đổi'):
            render_video.validate_brief(modified)
        both = copy.deepcopy(approved)
        both['aspect_ratio'] = 'both'
        with self.assertRaisesRegex(ValueError, 'thay đổi'):
            render_video.validate_brief(both)
        fresh_script = script()
        fresh_draft = core.draft_manifest(b, selection, fresh_script)
        fresh_conf = dict(conf, script_sha256=core.canonical_hash(fresh_draft))
        approved_both = core.approve_draft(fresh_draft, fresh_conf)
        render_video.validate_brief(approved_both)
        self.assertEqual(approved_both['aspect_ratio'],'both')

    def test_rank_uses_editor_estimates_only(self):
        r = core.check_bundle(bundle())
        self.assertEqual(len(r['editorial_ranking']), 1)
        self.assertTrue(r['ranking_is_editor_estimate'])
        self.assertGreater(r['editorial_ranking'][0]['editorial_priority_score'], 0)

    def test_prevent_output_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'result.json'
            core.write_new(p, {'ok': True})
            with self.assertRaises(FileExistsError):
                core.write_new(p, {'ok': False})

    def test_rss_group_exact_duplicate(self):
        objects = [{'id': 'a', 'headline': 'Science team launches satellite - Publisher A',
                    'published_at': NOW, 'source': 'A', 'rss_link': 'https://example.com/a'},
                   {'id': 'b', 'headline': 'Science team launches satellite - Publisher B',
                    'published_at': NOW, 'source': 'B', 'rss_link': 'https://example.org/b'}]
        result = rss.deduplicate(objects)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['candidate_count'], 2)

    def test_rss_parse_fixture_and_time_filter(self):
        xml = b'<rss><channel><item><title>Headline One</title><link>https://example.com/story</link><pubDate>Fri, 23 Oct 2026 12:00:00 GMT</pubDate></item></channel></rss>'
        now = dt.datetime(2026, 10, 23, 18, tzinfo=dt.timezone.utc)
        self.assertEqual(len(rss.parse_feed(xml, 'Test', 'https://example.com/feed', now, 24)), 1)
        self.assertEqual(len(rss.parse_feed(xml, 'Test', 'https://example.com/feed', now, 2)), 0)

    def test_preliminary_reader_extracts_text(self):
        p = reader.PublicArticle()
        p.feed('<html><head><meta property="og:title" content="Test News"></head><body><article><h1>Title</h1><p>Actual document sentence.</p><script>secret()</script></article></body></html>')
        self.assertIn('Actual document sentence.', p.parts)
        self.assertNotIn('secret()', p.parts)
        self.assertEqual(p.metadata['og:title'], 'Test News')

    def test_candidate_preview_is_unverified(self):
        input_data = {'country': 'US', 'category': 'science', 'hours': 24,
                      'collected_at': NOW, 'candidates': [{
                          'id': 'N-1', 'headline': 'Example ONLY', 'source': 'Test RSS',
                          'published_at': NOW, 'rss_link': 'https://example.com/1'}]}
        q, markdown = editor.preview_candidates(input_data)
        self.assertEqual(q['stories'][0]['verification'], 'UNVERIFIED')
        self.assertIn('CHƯA KIỂM CHỨNG', markdown)

if __name__ == '__main__':
    unittest.main()
