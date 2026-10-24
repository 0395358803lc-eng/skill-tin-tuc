"""Stage 2: portable Windows tool discovery and guarded bootstrap regression tests."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doctor
import runtime_tools


class Stage2RuntimeTests(unittest.TestCase):
    def test_explicit_browser_override_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            browser = Path(tmp) / "custom chrome.exe"
            browser.write_bytes(b"mock executable")
            self.assertEqual(runtime_tools.find_browser({"NEWS_CHROME_PATH": str(browser)}), browser.resolve())

    def test_invalid_override_does_not_silently_choose_another_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(runtime_tools.find_browser({"NEWS_CHROME_PATH": str(Path(tmp) / "missing.exe")}))

    def test_ffmpeg_prefers_runtime_and_blocks_unrecognized_tool_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            tool = root / "tools" / "ffmpeg-selected" / name
            tool.parent.mkdir(parents=True)
            tool.write_bytes(b"example")
            self.assertEqual(runtime_tools.find_media_binary(root, "ffmpeg"), str(tool.resolve()))
            with self.assertRaises(ValueError):
                runtime_tools.find_media_binary(root, "powershell")

    def test_ffmpeg_legacy_extracted_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
            tool = root / "tools" / "ffmpeg-extracted" / "version" / name
            tool.parent.mkdir(parents=True)
            tool.write_bytes(b"example")
            self.assertEqual(runtime_tools.find_media_binary(root, "ffprobe"), str(tool.resolve()))

    def test_encoder_probe_refuses_invalid_name(self):
        passed, detail = runtime_tools.probe_h264_encoder("ffmpeg", "arbitrary_unapproved")
        self.assertFalse(passed)
        self.assertIn("unavailable", detail)

    def test_encoder_probe_uses_real_frame_and_requested_encoder(self):
        with patch.object(runtime_tools, "run_probe", return_value=(True, "")) as run:
            ok, _ = runtime_tools.probe_h264_encoder("ffmpeg.exe", "libx264")
            self.assertTrue(ok)
            cmd = run.call_args.args[0]
            self.assertIn("libx264", cmd)
            self.assertIn("lavfi", cmd)
            self.assertIn("color=c=black:s=64x64:d=0.1", cmd)

    @staticmethod
    def mock_runtime(root: Path) -> None:
        for filename in (
            ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python",
            "models/vi_VN-vais1000-medium.onnx",
            "models/vi_VN-vais1000-medium.onnx.json",
            "models/en_US-lessac-medium.onnx",
            "models/en_US-lessac-medium.onnx.json",
            "remotion/node_modules/remotion/package.json",
            "remotion/src/News.jsx",
        ):
            p = root / filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"example")

    @staticmethod
    def probe_output(args, timeout=20):
        if "-filters" in args:
            return True, " T.C subtitles V->V Render text subtitles"
        if args[0] == "nvidia-smi":
            return False, "no NVIDIA GPU"
        return True, "ok"

    def diagnose_fixture(self, root: Path, nvenc: bool, cpu: bool):
        def encoder(_ffmpeg, name):
            success = nvenc if name == "h264_nvenc" else cpu
            return success, "pass" if success else "disabled"
        with (
            patch.object(doctor.tools, "find_media_binary", side_effect=lambda _rt, name: name + ".exe"),
            patch.object(doctor.tools, "find_browser", return_value=Path("C:/Example/Chrome/chrome.exe")),
            patch.object(doctor.tools, "run_probe", side_effect=self.probe_output),
            patch.object(doctor.tools, "probe_h264_encoder", side_effect=encoder),
        ):
            return doctor.diagnose(root)

    def test_cpu_fallback_when_nvenc_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.mock_runtime(root)
            report = self.diagnose_fixture(root, nvenc=False, cpu=True)
            self.assertEqual(report["recommended_encoder"], "cpu")
            self.assertTrue(report["ready_dual_aspect"], report["missing_requirements"])
            self.assertFalse(report["nvenc_operational"])

    def test_gpu_path_when_nvenc_operational(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.mock_runtime(root)
            report = self.diagnose_fixture(root, nvenc=True, cpu=True)
            self.assertEqual(report["recommended_encoder"], "nvenc")

    def test_missing_remotion_is_not_ready_to_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.mock_runtime(root)
            (root / "remotion/src/News.jsx").unlink()
            report = self.diagnose_fixture(root, nvenc=False, cpu=True)
            self.assertFalse(report["ready_to_render"])
            self.assertIn("remotion_source", report["missing_requirements"])

    def test_no_operational_encoder_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.mock_runtime(root)
            report = self.diagnose_fixture(root, nvenc=False, cpu=False)
            self.assertFalse(report["ready_dual_aspect"])
            self.assertIn("h264_encoder", report["missing_requirements"])

    def test_bootstrap_and_remotion_require_explicit_mutation(self):
        installer = (ROOT / "scripts/bootstrap_windows.ps1").read_text(encoding="utf-8")
        remotion = (ROOT / "scripts/setup_remotion.ps1").read_text(encoding="utf-8")
        self.assertIn("CheckOnly", installer)
        self.assertIn("if($CheckOnly)", installer)
        self.assertIn("Runtime cannot be nested inside Skill", installer)
        self.assertIn("runtime_safe", installer)
        self.assertIn("Will not replace existing dependency file", installer)
        self.assertIn("AllowSourceUpdate", remotion)
        self.assertIn("Will not overwrite different Remotion source", remotion)
        self.assertIn("npm.cmd", remotion)
        self.assertNotIn("Invoke-WebRequest", installer)
        self.assertNotIn("Invoke-WebRequest", remotion)

    def test_renderer_uses_browser_discovery(self):
        renderer = (ROOT / "scripts/video_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("runtime_tools.find_browser()", renderer)
        self.assertIn("'--browser-executable',str(browser)", renderer)
        self.assertNotIn("chrome='C:/Program Files/Google/Chrome/Application/chrome.exe'", renderer)


    @unittest.skipUnless(os.name == "nt", "Windows PowerShell only")
    def test_checkonly_does_not_create_runtime(self):
        import json
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "fresh-runtime"
            process = subprocess.run(
                ["powershell.exe", "-NoProfile", "-File",
                 str(ROOT / "scripts/bootstrap_windows.ps1"),
                 "-Runtime", str(root), "-CheckOnly"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(process.returncode, 2, process.stderr)
            report = json.loads(process.stdout)
            self.assertEqual(report["mode"], "CHECK_ONLY_NO_MUTATION")
            self.assertFalse(report["preflight_pass"])
            self.assertFalse(root.exists())

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell only")
    def test_preflight_rejects_nonempty_runtime_without_overwrite(self):
        import json
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "active-runtime"
            root.mkdir()
            marker = root / "DO_NOT_TOUCH.txt"
            marker.write_text("preserved", encoding="utf-8")
            process = subprocess.run(
                ["powershell.exe", "-NoProfile", "-File",
                 str(ROOT / "scripts/bootstrap_windows.ps1"),
                 "-Runtime", str(root), "-CheckOnly"],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(process.returncode, 2, process.stderr)
            report = json.loads(process.stdout)
            self.assertFalse(report["runtime_safe"])
            self.assertIn("runtime_safe", report["missing"])
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserved")


if __name__ == "__main__":
    unittest.main()

