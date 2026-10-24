"""Stage 2: editor-renderer contracts, immutable approved audio, and recovery guards.

All approvals, news and media in this module are synthetic unit-test fixtures.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import editorial_core as core
import video_pipeline as vp
import job_integrity as integrity
import workflow as wf
from test_editorial import bundle, script, NOW


class Stage2WorkflowTests(unittest.TestCase):
    def make_job(self,root:Path)->Path:
        args=SimpleNamespace(jobs_root=root,job_id="news-STAGE2-FIXTURE",
            country="US",category="science",hours=24,language="vi-VN",
            seconds=60,aspect="both",tone="neutral")
        job=Path(wf.init_job(args)["job_directory"])
        wf.write_once(job/"queue.json",{"stories":[]})
        evidence=root/"evidence.json"
        evidence.write_text(json.dumps(bundle()),encoding="utf-8")
        self.assertEqual(wf.checked_evidence(job,evidence)["eligible"],1)
        wf.select_stories(job,["EVENT-01"],"I choose synthetic EVENT-01",NOW)
        return job

    def create_audio_assets(self,j:Path)->dict:
        (j/"background.wav").write_bytes(b"Unit test only, not actual WAV")
        (j/"pronunciation.json").write_text(
            json.dumps({"NASA":"na sa"},ensure_ascii=False),encoding="utf-8")
        sc=script()
        sc.update({
            "music_path":"background.wav",
            "music_sha256":wf.filehash(j/"background.wav"),
            "music_license":"Synthetic fixture only: no actual music rights are claimed",
            "pronunciation_lexicon_path":"pronunciation.json",
            "pronunciation_lexicon_sha256":wf.filehash(j/"pronunciation.json"),
        })
        return sc

    def draft(self,j:Path,sc:dict)->dict:
        path=j.parent/"input-script.json"
        path.write_text(json.dumps(sc,ensure_ascii=False),encoding="utf-8")
        result=wf.script_draft(j,path)
        self.assertEqual(result["stage"],"AWAITING_APPROVAL")
        return wf.read(j/"draft.json")

    def approve(self,j:Path,draft:dict)->dict:
        confirmation={"confirmed_at":NOW,
            "user_confirmation":"Explicit approval simulated in isolated unit test only",
            "script_sha256":core.canonical_hash(draft),
            "approved_story_ids":["EVENT-01"]}
        path=j.parent/"consent.json"
        path.write_text(json.dumps(confirmation),encoding="utf-8")
        wf.approve(j,path)
        return wf.read(j/"approved.json")

    def test_07_twenty_scenes_shared_between_editor_and_renderer(self):
        b=bundle()
        selection=core.choose(b,core.check_bundle(b),["EVENT-01"],"Choose fake fixture",NOW)
        sc=script()
        scene={"type":"news_card","instruction":"Synthetic art","claim_ids":["C1"]}
        sc["stories"][0]["visual_plan"]=[scene.copy() for _ in range(20)]
        draft=core.draft_manifest(b,selection,sc)
        self.assertEqual(core.MAX_VISUAL_SCENES,20)
        self.assertEqual(len(draft["stories"][0]["visual_plan"]),20)
        from inspect import getsource
        self.assertIn("editorial.MAX_VISUAL_SCENES",getsource(vp.render))
        sc["stories"][0]["visual_plan"].append(scene)
        with self.assertRaisesRegex(ValueError,"1..20 scenes"):
            core.draft_manifest(b,selection,sc)

    def test_08_09_audio_paths_and_licenses_are_hashed_at_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            j=self.make_job(Path(temp))
            sc=self.create_audio_assets(j)
            draft=self.draft(j,sc)
            self.assertEqual(draft["music_path"],"background.wav")
            self.assertEqual(draft["pronunciation_lexicon_sha256"],sc["pronunciation_lexicon_sha256"])
            self.assertEqual(draft["music_license"],sc["music_license"])
            approved=self.approve(j,draft)
            self.assertEqual(wf.checked_local_asset(j,approved,"music"),j/"background.wav")
            self.assertEqual(wf.checked_local_asset(j,approved,"pronunciation_lexicon"),j/"pronunciation.json")
            self.assertEqual(vp.approved_audio_asset(approved,j,"music"),j/"background.wav")
            self.assertEqual(vp.approved_audio_asset(approved,j,"pronunciation_lexicon"),j/"pronunciation.json")
            self.assertEqual(core.canonical_hash(draft),
                approved["approval_record"]["approved_script_sha256"])
            with self.assertRaisesRegex(ValueError,"differs from approved"):
                vp.approved_audio_asset(approved,j,"music",j/"pronunciation.json")

    def test_08_09_modified_audio_is_rejected_before_new_render(self):
        with tempfile.TemporaryDirectory() as temp:
            j=self.make_job(Path(temp))
            approved=self.approve(j,self.draft(j,self.create_audio_assets(j)))
            original=wf.filehash(j/"approved.json")
            (j/"background.wav").write_bytes(b"Changed after approval")
            with patch.object(wf,"run_process") as worker:
                with self.assertRaisesRegex(ValueError,"checksum"):
                    wf.render_job(j)
                worker.assert_not_called()
            self.assertEqual(wf.filehash(j/"approved.json"),original)
            self.assertFalse((j/"attempt-01").exists())

    def test_08_09_missing_license_or_invalid_lexicon_block_draft(self):
        b=bundle()
        choice=core.choose(b,core.check_bundle(b),["EVENT-01"],"Choose",NOW)
        sc=script()
        sc["music_path"]="bg.wav"
        sc["music_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"license"):
            core.draft_manifest(b,choice,sc)
        sc.pop("music_path")
        sc.pop("music_sha256")
        sc["pronunciation_lexicon_path"]="../hidden.json"
        sc["pronunciation_lexicon_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"safe relative"):
            core.draft_manifest(b,choice,sc)
        sc["pronunciation_lexicon_path"]="lexicon.json"
        sc["pronunciation_lexicon_sha256"]="BAD"
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            core.draft_manifest(b,choice,sc)

    def test_09_workflow_passes_only_hashed_assets_and_scrubs_ambient_map(self):
        with tempfile.TemporaryDirectory() as temp:
            j=self.make_job(Path(temp))
            approved=self.approve(j,self.draft(j,self.create_audio_assets(j)))
            calls=[]
            def fake(argv,env,log,timeout=2700):
                calls.append((argv,env))
                out=Path(argv[argv.index("--out")+1])
                out.mkdir()
                (out/"qa_report.json").write_text(json.dumps({
                    "status":"TECHNICAL_PASS","demo":False,
                    "source_manifest":str(j/"approved.json"),
                    "formats":{"9:16":{},"16:9":{}}}),encoding="utf-8")
                return 0,"synthetic renderer"
            with patch.dict("os.environ",{"PIPER_PRONUNCIATION_MAP":str(j/"forged.json")}):
                with patch.object(wf,"run_process",side_effect=fake):
                    result=wf.render_job(j)
            self.assertEqual(result["stage"],"RENDERED")
            argv,env=calls[0]
            self.assertEqual(Path(argv[argv.index("--music")+1]),j/"background.wav")
            self.assertEqual(Path(argv[argv.index("--lexicon")+1]),j/"pronunciation.json")
            self.assertNotIn("PIPER_PRONUNCIATION_MAP",env)
            self.assertEqual(result["attempts"][0]["encoder"],"auto")
            self.assertEqual(wf.filehash(j/"approved.json"),wf.filehash(j/"approved.json"))

    def test_10_11_tampered_checkpoint_blocks_status_and_resume_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            j=self.make_job(Path(temp))
            wf.write_once(j/"draft.json",{"tampering":"synthetic extra uncheckpointed artifact"})
            view=wf.status(j)
            self.assertTrue(view["mutation_blocked"])
            self.assertIn("RECOVERY BLOCKED",view["next"])
            self.assertFalse(view["recovery"]["safe_to_mutate"])
            with self.assertRaisesRegex(ValueError,"blocked"):
                integrity.assert_action_allowed(j,"render")
            self.assertFalse((j/"approved.json").exists())

    def test_11_no_cpu_retry_on_license_failure_even_when_gpu_mentioned(self):
        with tempfile.TemporaryDirectory() as temp:
            j=self.make_job(Path(temp))
            self.approve(j,self.draft(j,script()))
            with patch.object(wf,"run_process",return_value=(2,"NVENC setup failed because copyright check failed")) as runner:
                with self.assertRaisesRegex(RuntimeError,"not a recognized GPU fault"):
                    wf.render_job(j)
            runner.assert_called_once()
            self.assertFalse((j/"render_result.json").exists())
            self.assertTrue(wf.status(j)["mutation_blocked"])

    def test_12_selection_cannot_be_reused_as_script_approval(self):
        b=bundle()
        choice=core.choose(b,core.check_bundle(b),["EVENT-01"],"Choose fake",NOW)
        draft=core.draft_manifest(b,choice,script())
        msg={"confirmed_at":NOW,"user_confirmation":"Choose fake",
             "approved_story_ids":["EVENT-01"],"script_sha256":core.canonical_hash(draft)}
        with self.assertRaisesRegex(ValueError,"distinct"):
            core.approve_draft(draft,msg)
        msg["user_confirmation"]="New approval, but old hash"
        draft["video_title"]="Changed after user reviewed"
        with self.assertRaisesRegex(ValueError,"changed"):
            core.approve_draft(draft,msg)


if __name__=="__main__":
    unittest.main()
