import copy
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import job_integrity as ji
import research_enrichment as re
import workflow as wf
import editorial_core as core
from test_editorial import bundle,NOW

class Stage16CrashAndLockTests(unittest.TestCase):
    def job(self,p:Path):
        args=SimpleNamespace(jobs_root=p,job_id='news-INTEGRITY-TEST',
          country='US',category='technology',hours=24,language='vi-VN',
          seconds=60,aspect='both',tone='neutral')
        return Path(wf.init_job(args)['job_directory'])

    def test_atomic_new_bytes_and_no_overwrite_or_partial_final(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'draft.json'
            ji.atomic_new(p,b'first')
            with self.assertRaises(FileExistsError):ji.atomic_new(p,b'different')
            self.assertEqual(p.read_bytes(),b'first')
            self.assertFalse(list(Path(t).glob('*.pending')))

    def test_new_job_has_verified_checkpoint_and_no_auto_approval(self):
        with tempfile.TemporaryDirectory() as t:
            j=self.job(Path(t))
            ck=ji.verify_checkpoint(j)
            self.assertEqual(ck['status'],'VERIFIED')
            plan=ji.recovery_plan(j)
            self.assertTrue(plan['safe_to_mutate'])
            self.assertTrue(plan['never_auto_approve_or_republish'])
            self.assertFalse((j/'approved.json').exists())

    def test_crash_after_artifact_before_event_is_inspect_not_redo(self):
        with tempfile.TemporaryDirectory() as t:
            j=self.job(Path(t))
            wf.write_once(j/'draft.json',{'status':'draft'})
            ck=ji.verify_checkpoint(j)
            self.assertEqual(ck['status'],'NEEDS_MANUAL_RECOVERY')
            self.assertIn('artifacts created since last checkpoint', ' '.join(ck['issues']))
            self.assertFalse(ji.recovery_plan(j)['safe_to_mutate'])
            self.assertEqual((j/'draft.json').read_text(encoding='utf-8').count('draft'),1)
            wf.event(j,'DRAFT',{'test':'synthetic'})
            self.assertEqual(ji.verify_checkpoint(j)['status'],'VERIFIED')

    def test_tampered_approved_file_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as t:
            j=self.job(Path(t))
            wf.write_once(j/'approved.json',{'status':'approved','stories':[]})
            wf.event(j,'APPROVAL_FIXTURE',{})
            (j/'approved.json').write_text('{"status":"altered"}',encoding='utf-8')
            self.assertIn('modified: approved.json',ji.verify_checkpoint(j)['issues'])
            self.assertFalse(ji.recovery_plan(j)['safe_to_mutate'])

    def test_active_lock_never_stolen_and_stale_requires_explicit_recovery(self):
        with tempfile.TemporaryDirectory() as t:
            j=self.job(Path(t))
            with ji.lock_job(j):
                self.assertEqual(ji.inspect_lock(j)['status'],'ACTIVE')
                with self.assertRaises(ValueError):ji.recover_stale_lock(j)
                with self.assertRaisesRegex(ValueError,'locked'):
                    with ji.lock_job(j):pass
            (j/'.stage4.lock').write_text(json.dumps({'pid':99999999,
                'created_at':'2020-01-01T00:00:00Z','token':'orphan'}))
            self.assertEqual(ji.inspect_lock(j)['status'],'STALE')
            self.assertFalse(ji.recovery_plan(j)['safe_to_mutate'])
            result=ji.recover_stale_lock(j)
            self.assertEqual(result['status'],'RECOVERED')
            self.assertFalse((j/'.stage4.lock').exists())
            self.assertTrue((j/'stale_lock_recovery.jsonl').is_file())

    def test_partial_checkpoint_tail_demands_manual_inspection(self):
        with tempfile.TemporaryDirectory() as t:
            j=self.job(Path(t))
            with (j/'checkpoints.jsonl').open('ab') as f:f.write(b'{"incomplete":true')
            ck=ji.verify_checkpoint(j)
            self.assertEqual(ck['status'],'NEEDS_MANUAL_RECOVERY')
            self.assertTrue(ck['truncated_tail'])

    def test_legacy_job_is_not_implicitly_verified(self):
        with tempfile.TemporaryDirectory() as t:
            j=Path(t)/'old';j.mkdir()
            self.assertEqual(ji.verify_checkpoint(j)['status'],'LEGACY_NO_CHECKPOINTS')
            self.assertFalse(ji.recovery_plan(j)['safe_to_mutate'])

class Stage17ProvenanceTests(unittest.TestCase):
    def sample(self):
        return copy.deepcopy(bundle())

    def test_canonical_url_removes_tracking_not_article_content(self):
        self.assertEqual(re.canonical_url('https://EXAMPLE.org/p/123/?utm_source=foo&id=9&fbclid=10'),
            'https://example.org/p/123?id=9')
        self.assertNotEqual(re.canonical_url('https://example.org/story?id=1'),
                            re.canonical_url('https://example.org/story?id=2'))

    def test_source_independence_is_per_claim_not_two_links(self):
        b=self.sample();s=b['stories'][0]
        independent=re.audited_sources(s)
        self.assertTrue(independent['claim_independence_pass'])
        s['claims'][0]['source_ids']=['SRC-A']
        self.assertFalse(re.audited_sources(s)['claim_independence_pass'])
        s['claims'][0]['source_ids']=['SRC-A','SRC-B']
        s['sources'][1]['ownership_group']='same-owner'
        s['sources'][0]['ownership_group']='same-owner'
        self.assertFalse(re.audited_sources(s)['claim_independence_pass'])

    def test_syndicated_or_unread_articles_do_not_count(self):
        b=self.sample();s=b['stories'][0]
        s['sources'][1]['syndicated_copy']=True
        self.assertFalse(re.audited_sources(s)['claim_independence_pass'])
        s['sources'][1]['syndicated_copy']=False
        s['sources'][1]['read_confirmed']=False
        self.assertFalse(re.audited_sources(s)['claim_independence_pass'])

    def test_stale_or_future_event_blocked_without_faking_freshness(self):
        b=self.sample();rep=core.check_bundle(b)
        self.assertEqual(re.research_review(b,rep,24)['eligible_count'],1)
        b['stories'][0]['event_at']='2026-10-20T12:00:00Z'
        stale=re.research_review(b,core.check_bundle(b),24)
        self.assertEqual(stale['eligible_count'],0)
        self.assertIn('EVENT_OUTSIDE_REQUESTED_WINDOW',stale['all_reviews'][0]['freshness_flags'])
        b['stories'][0]['event_at']='2026-10-26T12:00:00Z'
        self.assertIn('EVENT_TIME_IN_FUTURE',
             re.research_review(b,core.check_bundle(b),24)['all_reviews'][0]['freshness_flags'])

    def test_unverified_rss_shortlist_never_promotes_to_truth(self):
        data={'collected_at':NOW,'country':'US','category':'technology','hours':72,
              'candidates':[{'id':f'N-{i:02d}','headline':f'Example update on company {i} new product launch',
                'rss_link':f'https://news.example.org/story/{i}?utm_campaign=x',
                'source':'Example Publisher','published_at':'2026-10-23T17:00:00Z',
                'related_articles':[{'rss_link':f'https://news.example.org/story/{i}',
                   'headline':f'Example update on company {i} new product launch',
                   'source':'Example Publisher'}]} for i in range(18)]}
        out=re.group_rss(data,12)
        self.assertEqual(len(out['shortlist']),12)
        self.assertEqual(out['total_candidates'],18)
        self.assertFalse(out['eligibility_for_factual_publication'])
        self.assertTrue(all(not s['sources_are_independent'] for s in out['shortlist']))
        with self.assertRaises(ValueError):re.group_rss(data,18)

    def test_independent_gate_returns_at_most_twelve_with_human_selection(self):
        b=self.sample()
        for i in range(15):
            s=copy.deepcopy(b['stories'][0]);s['id']=f'NEWS-{i:02d}'
            b['stories'].append(s)
        report=re.research_review(b,core.check_bundle(b),72)
        self.assertLessEqual(len(report['shortlist']),12)
        self.assertFalse(report['auto_verified_truth'])
        self.assertTrue(report['user_selection_and_exact_script_approval_required'])

    def test_workflow_evidence_rejects_stale_event(self):
        with tempfile.TemporaryDirectory() as t:
            job=Stage16CrashAndLockTests().job(Path(t))
            wf.write_once(job/'queue.json',{'stories':[]})
            b=self.sample();b['stories'][0]['event_at']='2026-10-20T12:00:00Z'
            path=Path(t)/'evidence_input.json'
            path.write_text(json.dumps(b),encoding='utf-8')
            result=wf.checked_evidence(job,path)
            self.assertEqual(result['eligible'],0)
            self.assertEqual(wf.status(job)['stage'],'NEEDS_EVIDENCE')
            self.assertTrue((job/'stage17_evidence_review.json').exists())
            self.assertFalse((job/'selection.json').exists())

if __name__=='__main__':
    unittest.main()

class Stage16RenderReconciliationTests(unittest.TestCase):
    def args(self,root):
        from types import SimpleNamespace
        return SimpleNamespace(jobs_root=root,job_id='news-RECOVER-RENDER',
            country='US',category='technology',hours=24,language='vi-VN',
            seconds=60,aspect='both',tone='neutral')
    def approved(self,j):
        import editorial_core as core
        from test_editorial import script
        b=bundle()
        selected=core.choose(b,core.check_bundle(b),['EVENT-01'],
                'Unit test selection only',NOW)
        draft=core.draft_manifest(b,selected,script())
        conf={'confirmed_at':NOW,'user_confirmation':'Unit test only human gate fixture',
              'script_sha256':core.canonical_hash(draft),'approved_story_ids':['EVENT-01']}
        wf.write_once(j/'approved.json',core.approve_draft(draft,conf))
        wf.event(j,'UNIT_APPROVED',{ 'fixture':True})
    def test_completed_attempt_can_be_reconciled_without_changing_media(self):
        from test_editorial import script
        with tempfile.TemporaryDirectory() as t:
            j=Path(wf.init_job(self.args(Path(t)))['job_directory'])
            self.approved(j)
            folder=j/'attempt-01';folder.mkdir()
            for name in ('news_video_9x16.mp4','news_video_16x9.mp4'):
                (folder/name).write_bytes(b'UNIT_TEST_ONLY_'+name.encode('utf-8'))
            meta={'status':'TECHNICAL_PASS','demo':False,
                  'source_manifest':str(j/'approved.json'),
                  'formats':{'9:16':{'file':'news_video_9x16.mp4'},
                             '16:9':{'file':'news_video_16x9.mp4'}}}
            (folder/'qa_report.json').write_text(json.dumps(meta),encoding='utf-8')
            self.assertEqual(ji.recovery_plan(j)['suggested_stage'],'INTERRUPTED_RENDER_INSPECTION')
            self.assertFalse(ji.recovery_plan(j)['safe_to_mutate'])
            before={p.name:ji.sha256(p) for p in folder.glob('*.mp4')}
            with patch.object(wf.qa_engine,'analyze',return_value={
                'technical_pass':True,'errors':[],'demo':False,'formats':{}}):
                result=wf.reconcile_render(j)
            self.assertTrue(result['recovered'])
            self.assertEqual(result['stage'],'RENDERED')
            self.assertTrue(wf.read(j/'render_result.json')['recovered_after_interruption'])
            self.assertEqual(before,{p.name:ji.sha256(p) for p in folder.glob('*.mp4')})
            self.assertEqual(ji.verify_checkpoint(j)['status'],'VERIFIED')
            with self.assertRaisesRegex(ValueError,'already committed'):
                wf.reconcile_render(j)
    def test_incomplete_or_demo_render_never_reconciled(self):
        with tempfile.TemporaryDirectory() as t:
            j=Path(wf.init_job(self.args(Path(t)))['job_directory'])
            self.approved(j)
            folder=j/'attempt-01';folder.mkdir()
            with self.assertRaisesRegex(ValueError,'completed unique render'):
                wf.reconcile_render(j)
            (folder/'qa_report.json').write_text(json.dumps({
                'status':'TECHNICAL_PASS','demo':True,
                'source_manifest':str(j/'approved.json'),
                'formats':{'9:16':{'file':'missing.mp4'},'16:9':{'file':'missing2.mp4'}}}))
            with self.assertRaisesRegex(ValueError,'completed unique render'):
                wf.reconcile_render(j)
            self.assertFalse((j/'render_result.json').exists())

class Stage16InterprocessLockTests(unittest.TestCase):
    def test_real_process_contention_keeps_first_owner_lock(self):
        with tempfile.TemporaryDirectory() as t:
            j=Path(t)
            script='\\n'.join([
                'import pathlib,sys,time',
                'sys.path.insert(0,sys.argv[2])',
                'import job_integrity as i',
                'with i.lock_job(pathlib.Path(sys.argv[1])):',
                '    print("LOCKED",flush=True)',
                '    time.sleep(1.2)','']).replace('\\n',chr(10))
            p=subprocess.Popen([sys.executable,'-B','-c',script,str(j),str(ROOT/'scripts')],
               stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                first=p.stdout.readline().strip()
                if first!='LOCKED':
                    self.fail('lock subprocess startup failed: '+repr(first)+
                              ' stderr='+p.stderr.read()[:400])
                with self.assertRaisesRegex(ValueError,'locked'):
                    with ji.lock_job(j):pass
                self.assertEqual(ji.inspect_lock(j)['status'],'ACTIVE')
            finally:
                try:p.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    p.kill();p.wait()
                p.stdout.close()
                p.stderr.close()
            self.assertEqual(ji.inspect_lock(j)['status'],'UNLOCKED')

class Stage17ExtendedGateTests(unittest.TestCase):
    def test_future_published_source_blocks_story(self):
        b=copy.deepcopy(bundle())
        b['stories'][0]['sources'][0]['published_at']='2026-10-24T08:00:00Z'
        got=re.research_review(b,core.check_bundle(b),24)
        self.assertEqual(got['eligible_count'],0)
        self.assertIn('SOURCE_PUBLISHED_AFTER_EVIDENCE_SNAPSHOT:SRC-A',
                      got['all_reviews'][0]['freshness_flags'])

    def test_source_retrieved_before_publication_is_flagged(self):
        b=copy.deepcopy(bundle())
        b['stories'][0]['sources'][0]['published_at']='2026-10-23T17:50:00Z'
        b['stories'][0]['sources'][0]['retrieved_at']='2026-10-23T16:30:00Z'
        got=re.research_review(b,core.check_bundle(b),24)
        self.assertEqual(got['eligible_count'],0)
        self.assertTrue(any('SOURCE_RETRIEVED_BEFORE_PUBLICATION' in x
                          for x in got['all_reviews'][0]['freshness_flags']))

    def test_two_headlines_about_same_event_one_shortlist_slot(self):
        # These are deliberately near-identical strings: advisory title clustering.
        collected={'collected_at':NOW,'country':'US','category':'technology',
          'hours':24,'candidates':[{'id':'N-a','headline':'Company K announces new AI graphics chip today',
                'rss_link':'https://a.example.org/news/ai-chip',
                'source':'Publisher A','published_at':'2026-10-23T17:00:00Z'},
            {'id':'N-b','headline':'Company K announces new AI graphics chip today',
                'rss_link':'https://b.example.org/news/ai-chip',
                'source':'Publisher B','published_at':'2026-10-23T17:00:00Z'},
            {'id':'N-c','headline':'Government announces updated satellite plan today',
                'rss_link':'https://c.example.org/news/satellite',
                'source':'Publisher C','published_at':'2026-10-23T17:00:00Z'}]}
        out=re.group_rss(collected,12)
        self.assertEqual(out['total_candidates'],3)
        self.assertEqual(out['shortlist_count'],2)
        self.assertEqual(len(out['possible_event_groups']),2)
        self.assertTrue(any(g['discovery_count']==2 for g in out['possible_event_groups']))

    def test_no_fabricated_minimum_five_when_feed_has_three(self):
        data={'collected_at':NOW,'hours':24,'country':'US','category':'technology',
            'candidates':[{'id':f'N-{i}','headline':f'News about company {i} testing',
               'rss_link':f'https://example.org/{i}','source':'Example',
               'published_at':'2026-10-23T17:00:00Z'} for i in range(3)]}
        result=re.group_rss(data,12)
        self.assertLessEqual(result['shortlist_count'],3)
        self.assertFalse(result['eligibility_for_factual_publication'])

    def test_two_urls_one_article_still_rejected(self):
        b=copy.deepcopy(bundle())
        b['stories'][0]['sources'][1]['url']='https://EXAMPLE.com/sample-a?utm_source=elsewhere'
        self.assertFalse(re.audited_sources(b['stories'][0])['claim_independence_pass'])

    def test_discover_excludes_general_feed_for_tech_category(self):
        with tempfile.TemporaryDirectory() as t:
            job=Stage16CrashAndLockTests().job(Path(t))
            fake={'country':'US','category':'technology','hours':24,
             'collected_at':NOW,'candidates':[],'feed_results':[]}
            with patch.object(wf.rss,'fetch',return_value=fake) as call:
                result=wf.discover(job)
            self.assertEqual(result['stage'],'AWAITING_EVIDENCE')
            feeds=call.call_args.args[4]
            self.assertFalse(any('NPR' in x['name'] for x in feeds))
            self.assertTrue(any('The Verge' in x['name'] for x in feeds))
            self.assertTrue(any('Ars Technica' in x['name'] for x in feeds))
            self.assertTrue(any('TechCrunch' in x['name'] for x in feeds))
            self.assertEqual(ji.verify_checkpoint(job)['status'],'VERIFIED')
            self.assertFalse((job/'selection.json').exists())
