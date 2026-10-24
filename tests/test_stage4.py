import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import qa_engine as qa
import qa_repair as repair
import workflow as wf
import render_video as legacy
import editorial_core as core
from test_editorial import bundle, script, NOW

class Stage4Tests(unittest.TestCase):
    def test_srt_monotonic_validation(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/"cues.srt"
            legacy.write_srt([(0.,1.,"Hello"),(1.1,2.0,"World")],f)
            self.assertEqual(qa.verify_srt(f,3.)["cues"],2)
            legacy.write_srt([(0.,2.,"A"),(1.,2.5,"B")],f)
            with self.assertRaisesRegex(ValueError,"overlap"):
                qa.verify_srt(f,3.)
            legacy.write_srt([(0.,4.,"A")],f)
            with self.assertRaisesRegex(ValueError,"out of bounds"):
                qa.verify_srt(f,3.)
    def test_srt_reject_empty_text(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/"sub.srt"
            f.write_text("1\n00:00:00,100 --> 00:00:01,000\n\n",encoding="utf-8")
            with self.assertRaises(ValueError):qa.verify_srt(f,4.)
    def test_srt_bad_units(self):
        with self.assertRaises(ValueError):qa.srt_time("00:75:05,100")
    def test_repair_immutable_original(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);source=root/"original";source.mkdir()
            (source/"_work").mkdir()
            props={"cues":[{"start":.3,"end":1.5,"text":"Testing only."}]}
            (source/"_work"/"props-9x16.json").write_text(json.dumps(props),encoding="utf-8")
            (source/"qa_report.json").write_text(json.dumps({"formats":{"9:16":{"file":"video.mp4"}},
                  "duration_seconds":2.}),encoding="utf-8")
            (source/"video.mp4").write_bytes(b"TEST_ONLY_FAKE_VIDEO")
            q={"folder":str(source.resolve()),"errors":["MISSING_SRT:9:16"],"checked_at":NOW}
            result=repair.repair_srt_only(source,root/"repaired",q)
            self.assertIn("REGENERATE_SRT:9:16",result["changes"])
            self.assertFalse((source/"subtitles_9x16.srt").exists())
            self.assertEqual(qa.verify_srt(root/"repaired"/"subtitles_9x16.srt",2.)["cues"],1)
            with self.assertRaisesRegex(ValueError,"exists"):
                repair.repair_srt_only(source,root/"repaired",q)
    def test_repair_refuses_wrong_source_or_nontechnical(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"source";folder.mkdir()
            with self.assertRaisesRegex(ValueError,"non-repairable"):
                repair.repair_srt_only(folder,Path(td)/"new",{"errors":["MUTED_OR_MISSING_AUDIO:9:16"],"folder":str(folder)})
            with self.assertRaisesRegex(ValueError,"another"):
                repair.repair_srt_only(folder,Path(td)/"new",{"errors":["MISSING_SRT:9:16"],"folder":"elsewhere"})
    def args(self,root):
        return SimpleNamespace(jobs_root=root,job_id="news-UNITTEST",
            country="US",category="science",hours=24,
            language="vi-VN",seconds=60,aspect="both",tone="neutral")
    def test_init_status_and_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            arg=self.args(Path(td))
            obj=wf.init_job(arg)
            self.assertEqual(obj["stage"],"CREATED")
            with self.assertRaises(FileExistsError):wf.init_job(arg)
    def test_cannot_select_without_real_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            j=Path(wf.init_job(self.args(Path(td)))["job_directory"])
            with self.assertRaisesRegex(ValueError,"no evidence"):
                wf.select_stories(j,["EVENT-01"],"I select",NOW)
            with self.assertRaisesRegex(ValueError,"selection"):
                wf.script_draft(j,j/"script.json")
            with self.assertRaisesRegex(ValueError,"no draft"):
                wf.approve(j,j/"missing.json")
            with self.assertRaisesRegex(ValueError,"approval required"):
                wf.render_job(j)
            with self.assertRaisesRegex(ValueError,"technical QA"):
                wf.handoff(j)
    def test_draft_requires_matching_request(self):
        with tempfile.TemporaryDirectory() as td:
            j=Path(wf.init_job(self.args(Path(td)))["job_directory"])
            wf.write_once(j/"queue.json",{"stories":[]})
            external=Path(td)/"evidence.json"
            external.write_text(json.dumps(bundle()),encoding="utf-8")
            result=wf.checked_evidence(j,external)
            self.assertEqual(result["eligible"],1)
            wf.select_stories(j,["EVENT-01"],"I choose EVENT-01 as unit-test data",NOW)
            sc=script()
            sc["country"]="WORLD"
            source=Path(td)/"script.json"
            source.write_text(json.dumps(sc),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"country"):
                wf.script_draft(j,source)
    def test_draft_hash_approval_and_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            j=Path(wf.init_job(self.args(Path(td)))["job_directory"])
            wf.write_once(j/"queue.json",{"stories":[]})
            evidence=Path(td)/"evidence.json"
            evidence.write_text(json.dumps(bundle()),encoding="utf-8")
            wf.checked_evidence(j,evidence)
            wf.select_stories(j,["EVENT-01"],"I choose the fictional unit test EVENT-01",NOW)
            source=Path(td)/"script.json";source.write_text(json.dumps(script()),encoding="utf-8")
            draft=wf.script_draft(j,source)
            self.assertEqual(draft["stage"],"AWAITING_APPROVAL")
            self.assertIn("duration_advisory",draft)
            self.assertTrue((j/"duration_advisory.json").is_file())
            self.assertTrue(wf.status(j)["artifacts"]["duration_advisory.json"])
            bad=Path(td)/"bad.json"
            bad.write_text(json.dumps({"confirmed_at":NOW,"user_confirmation":"TEST FIXTURE ONLY",
                "script_sha256":"bad","approved_story_ids":["EVENT-01"]}),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"changed"):
                wf.approve(j,bad)
            good=Path(td)/"good.json"
            good.write_text(json.dumps({"confirmed_at":NOW,
              "user_confirmation":"TEST FIXTURE - simulated explicit approval only within unit test",
              "script_sha256":draft["script_sha256"],"approved_story_ids":["EVENT-01"]}),encoding="utf-8")
            result=wf.approve(j,good)
            self.assertEqual(result["stage"],"APPROVED")
            with self.assertRaisesRegex(ValueError,"already approved"):
                wf.approve(j,good)
            approved=wf.read(j/"approved.json")
            approved["stories"][0]["narration"]="modified"
            (j/"approved.json").write_text(json.dumps(approved),encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"thay đổi"):
                wf.status(j)
    def test_handoff_refuses_demo_and_failure(self):
        with tempfile.TemporaryDirectory() as td:
            j=Path(wf.init_job(self.args(Path(td)))["job_directory"])
            wf.write_once(j/"technical_qa.json",{"demo":True,"technical_pass":True})
            with self.assertRaisesRegex(ValueError,"DEMO"):
                wf.handoff(j)
    def test_prevent_media_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            j=Path(wf.init_job(self.args(Path(td)))["job_directory"])
            wf.write_once(j/"queue.json",{"stories":[]})
            ev=Path(td)/"ev.json";ev.write_text(json.dumps(bundle()),encoding="utf-8")
            wf.checked_evidence(j,ev)
            wf.select_stories(j,["EVENT-01"],"Select fictional fixture",NOW)
            scene={"type":"licensed_image","instruction":"test-only media",
                   "media_path":"image.jpg","license_evidence":"TEST file"}
            sc=script();sc["stories"][0]["visual_plan"]=[dict(scene,claim_ids=["C1"],media_sha256="0"*64)]
            p=Path(td)/"script.json";p.write_text(json.dumps(sc),encoding="utf-8")
            (j/"image.jpg").write_bytes(b"ORIGINAL_TEST")
            with self.assertRaisesRegex(ValueError,"checksum"):
                wf.script_draft(j,p)

if __name__=="__main__":unittest.main()

class Stage4RecoveryTests(unittest.TestCase):
    def new_job(self,root):
        args=SimpleNamespace(jobs_root=root,job_id="test-EXTRA",
            country="US",category="science",hours=24,language="vi-VN",
            seconds=60,aspect="both",tone="neutral")
        return Path(wf.init_job(args)["job_directory"])
    def approved(self,j):
        b=bundle()
        selection=core.choose(b,core.check_bundle(b),["EVENT-01"],"Simulated test only",NOW)
        draft=core.draft_manifest(b,selection,script())
        conf={"confirmed_at":NOW,"user_confirmation":"ONLY A UNIT TEST APPROVAL",
              "approved_story_ids":["EVENT-01"],"script_sha256":core.canonical_hash(draft)}
        wf.write_once(j/"approved.json",core.approve_draft(draft,conf))
    def test_parallel_lock(self):
        with tempfile.TemporaryDirectory() as td:
            j=self.new_job(Path(td))
            with wf.locked(j):
                with self.assertRaisesRegex(ValueError,"locked"):
                    with wf.locked(j):
                        pass
            self.assertFalse((j/".stage4.lock").exists())
    def test_gpu_recovery_is_single_cpu_retry(self):
        with tempfile.TemporaryDirectory() as td:
            j=self.new_job(Path(td));self.approved(j)
            original=wf.filehash(j/"approved.json")
            called=[]
            def fake(argv,env,log,timeout=2700):
                mode=argv[argv.index("--encoder")+1]
                called.append(mode)
                if mode=="auto":
                    return 2,"NVENC setup failed"
                folder=Path(argv[argv.index("--out")+1]);folder.mkdir()
                (folder/"qa_report.json").write_text(json.dumps({
                    "status":"TECHNICAL_PASS","demo":False,
                    "source_manifest":str(j/"approved.json"),
                    "formats":{"9:16":{},"16:9":{}}}),encoding="utf-8")
                return 0,"OK synthetic test"
            with patch.object(wf,"run_process",side_effect=fake):
                outcome=wf.render_job(j,encoder="auto")
            self.assertEqual(outcome["stage"],"RENDERED")
            self.assertEqual(called,["auto","cpu"])
            self.assertEqual(wf.filehash(j/"approved.json"),original)
    def test_no_retry_for_non_gpu_errors(self):
        with tempfile.TemporaryDirectory() as td:
            j=self.new_job(Path(td));self.approved(j)
            with patch.object(wf,"run_process",return_value=(2,"copyright validation failed")) as mock:
                with self.assertRaisesRegex(RuntimeError,"not a recognized GPU fault"):
                    wf.render_job(j,encoder="auto")
                self.assertEqual(mock.call_count,1)
            self.assertFalse((j/"render_result.json").exists())
    def test_handoff_rejects_tampered_video_and_never_autoposts(self):
        with tempfile.TemporaryDirectory() as td:
            j=self.new_job(Path(td));self.approved(j)
            out=j/"attempt-01";out.mkdir()
            (out/"clip.mp4").write_bytes(b"NOT A REAL VIDEO - UNIT TEST")
            (out/"subtitles_9x16.srt").write_text("TEST",encoding="utf-8")
            for name in ["sources.json","publishing_metadata.json",
                         "media_rights.json","qa_report.json"]:
                (out/name).write_text("{}",encoding="utf-8")
            (out/"narration.wav").write_bytes(b"synthetic fixture")
            report={"demo":False,"technical_pass":True,"warnings":[],
                    "eligible_for_automatic_publication":False,
                    "formats":{"9:16":{"video":"clip.mp4","width":1080,"sha256":"BAD"}}}
            wf.write_once(j/"technical_qa.json",report)
            wf.write_once(j/"delivery_pointer.json",{
                "output_directory":str(out),"approved_hash":wf.filehash(j/"approved.json")})
            with self.assertRaisesRegex(ValueError,"MP4 content changed"):
                wf.handoff(j)
            report["formats"]["9:16"]["sha256"]=wf.filehash(out/"clip.mp4")
            (j/"technical_qa.json").write_text(json.dumps(report),encoding="utf-8")
            handoff=wf.handoff(j)
            self.assertEqual(handoff["status"],"AWAITING_HUMAN_FINAL_REVIEW")
            self.assertFalse(handoff["ready_for_publication"])
            self.assertFalse(handoff["auto_uploaded"])

class Stage4RealSourceGuards(unittest.TestCase):
    def fake_bundle(self,folder,with_rights=True):
        folder.mkdir()
        (folder/"demo.mp4").write_bytes(b"X"*1600)
        (folder/"subtitles_9x16.srt").write_text(
            "1\n00:00:00,200 --> 00:00:01,500\nFixture only\n",encoding="utf-8")
        (folder/"qa_report.json").write_text(json.dumps({
            "status":"TECHNICAL_PASS","demo":False,"Piper_TTS":True,
            "source_manifest":"D:/fake/approved.json",
            "target_seconds":30,"duration_seconds":2.0,
            "formats":{"9:16":{"file":"demo.mp4"}}}),encoding="utf-8")
        (folder/"sources.json").write_text(json.dumps([{
            "headline":"Synthetic QA test","sources":[
                {"url":"https://example.com/news"},{"url":"https://example.org/news"}]}]),encoding="utf-8")
        (folder/"publishing_metadata.json").write_text("{}",encoding="utf-8")
        (folder/"narration.wav").write_bytes(b"WAVE")
        if with_rights:
            (folder/"media_rights.json").write_text(json.dumps({
                "media":[],"rights_status":"REVIEW_REQUIRED_BEFORE_PUBLICATION"}),encoding="utf-8")
    def fake_probe(self,unused):
        return {"format":{"duration":"2.0"},"streams":[
            {"codec_type":"video","codec_name":"h264","width":1080,"height":1920,"avg_frame_rate":"30/1"},
            {"codec_type":"audio","codec_name":"aac"}]}
    def fake_audio(self,unused):
        return {"mean_dB":-18.0,"peak_dB":-2.0,
            "longest_silence_seconds":0.,"silence_segments_over_1_5s":0}
    def test_real_placeholder_sources_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"episode";self.fake_bundle(folder)
            with patch.object(qa,"probe",side_effect=self.fake_probe),patch.object(qa,"audio_scan",side_effect=self.fake_audio):
                result=qa.analyze(folder,Path(td)/"qa.json","9:16",False)
            self.assertFalse(result["technical_pass"])
            self.assertIn("PLACEHOLDER_SOURCE_URL",result["errors"])
    def test_real_missing_media_rights_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)/"episode";self.fake_bundle(folder,False)
            with patch.object(qa,"probe",side_effect=self.fake_probe),patch.object(qa,"audio_scan",side_effect=self.fake_audio):
                result=qa.analyze(folder,Path(td)/"qa.json","9:16",False)
            self.assertFalse(result["technical_pass"])
            self.assertIn("MISSING_MEDIA_RIGHTS_LEDGER",result["errors"])
