"""Stage 6 release gate never elevates RC source/FFmpeg smoke to GA evidence."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import stage6_release_gate as gate

class Stage6ReleaseGateTests(unittest.TestCase):
    def test_source_only_is_not_ga(self):
        report=gate.evaluate(ROOT)
        self.assertEqual(report["status"],"RC_READY_WINDOWS_ACCEPTANCE_PENDING")
        self.assertTrue(report["checks"]["rc_source_manifest_verified"])
        self.assertFalse(report["checks"]["independent_windows_pipeline_verified"])
        self.assertFalse(report["ga_tag_created"])
        self.assertFalse(report["github_ga_release_published"])
        self.assertIn("MISSING_INDEPENDENT_WINDOWS_PIPER_REMOTION_FFMPEG_REPORT",report["pending"])

    def test_synthetic_ffmpeg_smoke_never_unlocks_ga(self):
        fake={"schema":"STAGE5_SYNTHETIC_MEDIA_QA_V1","status":"SYNTHETIC_MEDIA_QA_PASS",
              "outputs_checked":8,"remotion_rendered":False,"real_piper_tts":False,
              "results":[]}
        report=gate.evaluate(ROOT,windows_report=fake,review={"operator_approved_ga":True})
        self.assertEqual(report["status"],"RC_READY_WINDOWS_ACCEPTANCE_PENDING")
        self.assertIn("INCOMPLETE_OR_FAILED_WINDOWS_FULL_PIPELINE_PROFILES",report["pending"])
        self.assertFalse(report["checks"]["human_audio_visual_approval_verified"])

    def test_fake_profile_results_fail_without_human_signoff(self):
        fake={"schema":"STAGE5_WINDOWS_LOCAL_ACCEPTANCE_V1",
              "status":"LOCAL_TECHNICAL_QA_PASS","real_piper_tts":True,"remotion_rendered":True,
              "results":[{"target_seconds":n,"status":"LOCAL_TECHNICAL_QA_PASS",
                          "issues":[],"duration_seconds":{"9:16":n,"16:9":n}}
                         for n in (30,60,90,180)]}
        report=gate.evaluate(ROOT,windows_report=fake)
        self.assertTrue(report["checks"]["independent_windows_pipeline_verified"])
        self.assertFalse(report["checks"]["human_audio_visual_approval_verified"])
        self.assertFalse(report["ga_tag_created"])
        self.assertEqual(report["status"],"RC_READY_WINDOWS_ACCEPTANCE_PENDING")

if __name__=="__main__":
    unittest.main()
