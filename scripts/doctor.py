#!/usr/bin/env python3
"""Read-only diagnostics for the portable AI News Video Windows runtime."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import runtime_tools as tools

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = ROOT.parent / (ROOT.name + "-runtime")


def diagnose(runtime: Path) -> dict:
    runtime = runtime.resolve()
    venv = runtime / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    ffmpeg = tools.find_media_binary(runtime, "ffmpeg")
    ffprobe = tools.find_media_binary(runtime, "ffprobe")
    browser = tools.find_browser()
    models = {
        voice: (runtime / "models" / (voice + ".onnx")).is_file()
        and (runtime / "models" / (voice + ".onnx.json")).is_file()
        for voice in ("vi_VN-vais1000-medium", "en_US-lessac-medium")
    }
    py_ok, py_info = (
        tools.run_probe([str(venv), "-c",
                         "import PIL,piper,numpy;print('Pillow '+PIL.__version__+'; Piper import OK')"])
        if venv.is_file() else (False, "missing isolated Python venv")
    )
    cv_ok, cv_info = (
        tools.run_probe([str(venv), "-c",
                         "import cv2,pathlib;print('OpenCV '+cv2.__version__+'; Haar '+str(pathlib.Path(cv2.data.haarcascades,'haarcascade_frontalface_default.xml').is_file()))"])
        if venv.is_file() else (False, "missing isolated Python venv")
    )
    filter_ok, filters = tools.run_probe([ffmpeg, "-hide_banner", "-filters"]) if ffmpeg else (False, "")
    probe_ok, _ = tools.run_probe([ffprobe, "-version"]) if ffprobe else (False, "")
    ffmpeg_subtitles = filter_ok and any(
        line.split() and "subtitles" == line.split()[1]
        for line in filters.splitlines() if len(line.split()) >= 2
    )
    node_ok, node_info = tools.run_probe([shutil.which("node.exe") or shutil.which("node") or "node", "--version"])
    npm_bin = shutil.which("npm.cmd") or shutil.which("npm") or "npm.cmd"
    npm_ok, npm_info = tools.run_probe([npm_bin, "--version"])
    gpu_ok, gpu_info = tools.run_probe(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]
    )
    nvenc_ok, nvenc_detail = tools.probe_h264_encoder(ffmpeg, "h264_nvenc")
    cpu_ok, cpu_detail = tools.probe_h264_encoder(ffmpeg, "libx264")
    remotion = runtime / "remotion"
    required = {
        "python_packages": py_ok,
        "ffmpeg_subtitles": ffmpeg_subtitles,
        "ffprobe": probe_ok,
        "vietnamese_voice": models["vi_VN-vais1000-medium"],
        "english_voice": models["en_US-lessac-medium"],
    }
    advanced = {
        "node": node_ok, "npm": npm_ok, "chrome": browser is not None,
        "remotion_packages": (remotion / "node_modules" / "remotion").is_dir(),
        "remotion_source": (remotion / "src" / "News.jsx").is_file(),
        "dual_aspect_pipeline": (ROOT / "scripts" / "video_pipeline.py").is_file(),
    }
    ready = all(required.values()) and all(advanced.values()) and (nvenc_ok or cpu_ok)
    missing = [key for key, ok in {**required, **advanced}.items() if not ok]
    if not (nvenc_ok or cpu_ok):
        missing.append("h264_encoder")
    suggestions = {
        "python_packages": "Create an isolated Python 3.13 venv and install requirements-smart-crop.txt",
        "ffmpeg_subtitles": "Provide FFmpeg built with the subtitles/libass filter",
        "ffprobe": "Provide ffprobe.exe together with FFmpeg",
        "vietnamese_voice": "Supply licensed vi_VN-vais1000-medium.onnx and .onnx.json",
        "english_voice": "Supply licensed en_US-lessac-medium.onnx and .onnx.json",
        "node": "Install Node.js",
        "npm": "Install npm with Node.js",
        "chrome": "Install Chrome/Chromium, or set NEWS_CHROME_PATH",
        "remotion_packages": "Run setup_remotion.ps1 -InstallPackages in a separate runtime",
        "remotion_source": "Run setup_remotion.ps1 to copy the Remotion source to runtime",
        "dual_aspect_pipeline": "Restore missing video_pipeline.py from the Skill source",
        "h264_encoder": "Provide FFmpeg with working libx264 or NVIDIA NVENC",
    }
    return {
        "project": str(ROOT), "runtime": str(runtime),
        "checks": required, "dual_aspect_checks": advanced,
        "ready_dual_aspect": ready, "ready_to_render": ready,
        "stage18_voice_caption": {
            "local_piper_available": py_ok and all(models.values()),
            "narration_qa_source": (ROOT / "scripts" / "narration_quality.py").is_file(),
        },
        "stage19_smart_crop": {
            "opencv_local": cv_ok, "opencv_detail": cv_info,
            "smart_media_source": (ROOT / "scripts" / "smart_media.py").is_file(),
            "video_dynamic_crop_ready": cv_ok and bool(ffmpeg) and (nvenc_ok or cpu_ok),
        },
        "browser_path": str(browser) if browser else None,
        "browser_override": os.environ.get("NEWS_CHROME_PATH") or os.environ.get("REMOTION_BROWSER_EXECUTABLE"),
        "node": node_info if node_ok else None, "npm": npm_info if npm_ok else None,
        "python": py_info,
        "gpu": gpu_info,
        "nvidia_gpu_detected": gpu_ok,
        "nvenc_operational": nvenc_ok, "nvenc_detail": "pass" if nvenc_ok else nvenc_detail,
        "cpu_h264_operational": cpu_ok, "cpu_h264_detail": "pass" if cpu_ok else cpu_detail,
        "recommended_encoder": "nvenc" if nvenc_ok else ("cpu" if cpu_ok else None),
        "ffmpeg": ffmpeg, "ffprobe": ffprobe,
        "missing_requirements": missing,
        "recommended_actions": [suggestions[name] for name in missing],
        "note": "CPU x264 is a verified fallback only when libx264 probe passes; source QA and media rights still require human review.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path,
                        default=Path(os.environ.get("NEWS_SKILL_RUNTIME", DEFAULT_RUNTIME)))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = diagnose(args.runtime)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output)
    if args.out:
        if args.out.exists():
            parser.error("Diagnostic report exists; will not overwrite")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as output_file:
            output_file.write(output + "\n")
    sys.exit(0 if report["ready_dual_aspect"] else 2)


if __name__ == "__main__":
    main()
