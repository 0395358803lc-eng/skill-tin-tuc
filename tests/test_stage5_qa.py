"""Stage 5 QA regression and realistic acceptance-scope tests; no real news used."""
from __future__ import annotations
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import qa_engine as qa
import stage5_fixture
import stage5_media_smoke
import stage5_perf_audit as perf
import video_pipeline as pipeline

class Stage5QARegression(unittest.TestCase):
    def folder(self,root:Path,duration=30):
        folder=root/"export";folder.mkdir()
        (folder/"DEMO_DO_NOT_PUBLISH_9x16.mp4").write_bytes(b'SYNTHETIC_NOT_VIDEO'*100)
        (folder/"qa_report.json").write_text(json.dumps({
            "demo":True,"status":"TECHNICAL_PASS","duration_seconds":duration,
            "target_seconds":duration,
            "formats":{"9:16":{"file":"DEMO_DO_NOT_PUBLISH_9x16.mp4"}},
            "Piper_TTS":False}),encoding="utf-8")
        (folder/"sources.json").write_text(json.dumps([{
            "headline":"Synthetic fixture only",
            "sources":[{"url":"https://example.org/1"},{"url":"https://example.net/2"}]}]),encoding="utf-8")
        (folder/"publishing_metadata.json").write_text("{}")
        (folder/"narration.wav").write_bytes(b'SYNTHETIC')
        (folder/"media_rights.json").write_text('{"rights_status":"REVIEW_REQUIRED_BEFORE_PUBLICATION"}')
        (folder/"subtitles_9x16.srt").write_text(
            "1\n00:00:00,000 --> 00:00:09,900\nSynthetic news QA only\n\n"
            "2\n00:00:10,000 --> 00:00:19,900\nAnother synthetic caption\n\n"
            "3\n00:00:20,000 --> 00:00:29,900\nFinal synthetic caption\n",encoding="utf-8")
        return folder

    def qa(self,folder,duration=30,*,audio=None,previews=None):
        info={"streams":[{"codec_type":"video","width":1080,"height":1920,
            "codec_name":"h264","avg_frame_rate":"30/1"},
            {"codec_type":"audio","codec_name":"aac"}],"format":{"duration":str(duration)}}
        sound=audio or {"peak_dB":-2.,"mean_dB":-18.,"longest_silence_seconds":0.}
        frames=previews if previews is not None else [
            {"near_black":False},{"near_black":False},{"near_black":False}]
        with patch.object(qa,"probe",return_value=info),patch.object(qa,"audio_scan",return_value=sound),patch.object(qa,"previews",return_value=frames):
            return qa.analyze(folder,folder.parent/"report.json","9:16",frames=True)

    def test_26_integrity_existing_approvals_do_not_change_for_qa(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.folder(Path(tmp))
            before={p.name:qa.digest(p) for p in folder.iterdir() if p.is_file()}
            self.assertTrue(self.qa(folder)["technical_pass"])
            self.assertEqual(before,{p.name:qa.digest(p) for p in folder.iterdir() if p.is_file()})

    def test_27_corrupt_srt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.folder(Path(tmp))
            path=folder/"subtitles_9x16.srt"
            path.write_text(path.read_text()+"\ufffd",encoding="utf-8")
            result=self.qa(folder)
            self.assertFalse(result["technical_pass"])
            self.assertTrue(any("INVALID_SRT:9:16" in x for x in result["errors"]))

    def test_27_severe_caption_coverage_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.folder(Path(tmp))
            (folder/"subtitles_9x16.srt").write_text(
                "1\n00:00:00,000 --> 00:00:02,000\nShort caption\n")
            obj=self.qa(folder)
            self.assertIn("CAPTION_COVERAGE_CRITICALLY_LOW:9:16",obj["errors"])

    def test_27_severe_caption_length_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.folder(Path(tmp))
            (folder/"subtitles_9x16.srt").write_text(
                "1\n00:00:00,000 --> 00:00:29,900\n"+"X"*113+"\n")
            obj=self.qa(folder)
            self.assertIn("CAPTION_COPY_SEVERE_OVERFLOW_RISK:9:16",obj["errors"])

    def test_27_black_frames_block_only_when_repeated(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.folder(Path(tmp))
            frames=[{"near_black":True},{"near_black":True},{"near_black":False}]
            obj=self.qa(folder,previews=frames)
            self.assertIn("MULTIPLE_NEAR_BLACK_FRAMES:9:16",obj["errors"])
            self.assertFalse(obj["technical_pass"])
            single=self.qa(folder,previews=[{"near_black":False},{"near_black":True}])
            self.assertTrue(single["technical_pass"])
            self.assertIn("POSSIBLE_BLACK_FRAME:9:16",single["warnings"])

    def test_27_loud_or_silent_audio_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=self.folder(Path(tmp))
            loud=self.qa(folder,audio={"peak_dB":-0.05,"mean_dB":-1,"longest_silence_seconds":0})
            self.assertIn("UNSAFELY_LOUD_AVERAGE_AUDIO:9:16",loud["errors"])
            self.assertIn("AUDIO_PEAK_NEAR_ZERO_DB_REVIEW:9:16",loud["warnings"])
            silent=self.qa(folder,audio={"peak_dB":-9,"mean_dB":-38,"longest_silence_seconds":28})
            self.assertIn("EXCESSIVE_AUDIO_SILENCE:9:16",silent["errors"])

    def test_27_static_layout_detects_risk_not_visual_truth(self):
        safe={"stories":[{"headline":"Good","summary":"Good summary","shots":[{}]}],
              "cues":[{"text":"Hello"}]}
        self.assertEqual(qa.inspect_caption_and_layout(safe,"9:16"),[])
        unsafe={"stories":[{"headline":"H"*236,"summary":"Synthetic","shots":[]}],
                "cues":[{"text":"S"*112}]}
        issues=qa.inspect_caption_and_layout(unsafe,"9:16")
        self.assertEqual(len([r for r in issues if r["severity"]=="ERROR"]),2)

    def test_28_four_timing_profiles_both_aspects_are_demo(self):
        for seconds in (30,60,90,180):
            brief=stage5_fixture.make(seconds,"vi-VN","both")
            self.assertTrue(brief["demo"])
            self.assertEqual(brief["target_seconds"],seconds)
            self.assertEqual(brief["aspect_ratio"],"both")
            self.assertEqual(set(pipeline.FORMATS),{"9:16","16:9"})
            self.assertIn("DO NOT PUBLISH",brief["video_title"])
        self.assertEqual(stage5_media_smoke.DURATIONS,(30,60,90,180))

    def test_28_reject_overwriting_ffmpeg_smoke_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):
                stage5_media_smoke.run(Path(tmp))

    def test_29_resource_audit_never_invents_gpu_or_perf(self):
        qa_data={"technical_pass":True,"errors":[],"formats":{
            ratio:{"duration_seconds":60} for ratio in perf.ASPECTS}}
        measured={"returncode":0,"timeout":False,"startup_stall_detected":False,
            "remotion_sample_every":1,"native_motion_fps":30,
            "renderer_qa":{"formats":{r:{"encoder":"libx264"} for r in perf.ASPECTS}},
            "elapsed_seconds":100.5,"peak_process_tree_rss_mb":500.0,
            "sample_count":2,"samples":[{},{}]}
        auto=perf.assess(measured,qa_data,60,"auto")
        self.assertEqual(auto["status"],"LOCAL_TECHNICAL_QA_PASS")
        self.assertFalse(auto["gpu_selected_for_both_aspects"])
        self.assertIsNone(auto["device_gpu_used_mb"])
        bad=perf.assess(measured,qa_data,60,"nvenc")
        self.assertIn("NVENC_ENCODER_NOT_SELECTED:9:16",bad["issues"])
        self.assertEqual(bad["status"],"LOCAL_TECHNICAL_QA_FAIL")
        with patch.object(pipeline.legacy,"nvenc_available",return_value=False):
            self.assertEqual(pipeline.select_encoder("auto"),"libx264")
            with self.assertRaisesRegex(RuntimeError,"NVENC"):
                pipeline.select_encoder("nvenc")

    def test_29_duration_drift_fails_local_acceptance(self):
        measured={"returncode":0,"timeout":False,"startup_stall_detected":False,
                  "remotion_sample_every":1,"native_motion_fps":30,
                  "renderer_qa":{"formats":{r:{"encoder":"libx264"} for r in perf.ASPECTS}},
                  "elapsed_seconds":90,"peak_process_tree_rss_mb":200,
                  "sample_count":1,"samples":[{}]}
        data={"technical_pass":True,"errors":[],"formats":{
            ratio:{"duration_seconds":92} for ratio in perf.ASPECTS}}
        assert any(x.startswith("VIDEO_DURATION_OUTSIDE_5PCT:")
                   for x in perf.assess(measured,data,60,"cpu")["issues"])

if __name__=="__main__":
    unittest.main()
