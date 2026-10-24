#!/usr/bin/env python3
"""Read-only discovery of Windows video tooling; no downloads or installations."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def find_browser(environment: dict[str, str] | None = None) -> Path | None:
    """Honor explicit browser configuration, then inspect PATH and standard install locations."""
    env = os.environ if environment is None else environment
    configured = env.get("NEWS_CHROME_PATH") or env.get("REMOTION_BROWSER_EXECUTABLE")
    if configured:
        candidate = Path(configured.strip('"'))
        return candidate.resolve() if candidate.is_file() else None
    for binary in ("chrome", "chrome.exe", "chromium", "chromium.exe", "chromium-browser"):
        result = shutil.which(binary, path=env.get("PATH"))
        if result and Path(result).is_file():
            return Path(result).resolve()
    bases = [env.get(k, "") for k in ("PROGRAMFILES", "PROGRAMW6432", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    # Windows standard paths are checked even when these environment variables are missing.
    if os.name == "nt":
        bases += ["C:/Program Files", "C:/Program Files (x86)"]
    seen: set[str] = set()
    for base in bases:
        if not base:
            continue
        for suffix in ("Google/Chrome/Application/chrome.exe",
                       "Chromium/Application/chrome.exe",
                       "Chromium/Application/chromium.exe"):
            candidate = Path(base) / suffix
            if str(candidate).lower() in seen:
                continue
            seen.add(str(candidate).lower())
            if candidate.is_file():
                return candidate.resolve()
    return None


def find_media_binary(runtime: Path, name: str) -> str | None:
    """Choose runtime-installed binaries before system PATH; preserve legacy extracted tools."""
    if name not in ("ffmpeg", "ffprobe"):
        raise ValueError("Unsupported media tool")
    exe = name + (".exe" if os.name == "nt" else "")
    preferred = runtime / "tools" / "ffmpeg-selected" / exe
    if preferred.is_file():
        return str(preferred.resolve())
    extracted = runtime / "tools" / "ffmpeg-extracted"
    if extracted.is_dir():
        for item in sorted(extracted.rglob(exe)):
            if item.is_file():
                return str(item.resolve())
    return shutil.which(name)


def run_probe(args: list[str], timeout: int = 20) -> tuple[bool, str]:
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                encoding="utf-8", errors="replace", timeout=timeout)
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return False, str(exc)


def probe_h264_encoder(ffmpeg: str | None, encoder: str) -> tuple[bool, str]:
    """Encode a real synthetic frame. Encoder listings alone are not proof of support."""
    if not ffmpeg or encoder not in ("libx264", "h264_nvenc"):
        return False, "encoder unavailable"
    return run_probe([ffmpeg, "-hide_banner", "-loglevel", "error",
                      "-f", "lavfi", "-i", "color=c=black:s=64x64:d=0.1",
                      "-frames:v", "1", "-c:v", encoder, "-f", "null", "-"], timeout=30)
