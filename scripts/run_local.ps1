param(
    [Parameter(Mandatory=$true)][string]$InputFile,
    [string]$OutputDir = '',
    [string]$Voice = 'vi_VN-vais1000-medium',
    [ValidateSet('auto','cpu','nvenc')][string]$Encoder = 'auto',
    [switch]$DryRun,
    [switch]$AllowDemo,
    [switch]$DemoSilence,
    [switch]$AllowLonger
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$parent = Split-Path -Parent $root
$name = Split-Path -Leaf $root
$runtime = if ($env:NEWS_SKILL_RUNTIME) { $env:NEWS_SKILL_RUNTIME } else { Join-Path $parent ($name + '-runtime') }
$python = Join-Path $runtime '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw "Missing Python runtime: $python" }
$tools = Join-Path $runtime 'tools\ffmpeg-extracted'
$selected = Join-Path $runtime 'tools\ffmpeg-selected\ffmpeg.exe'
$ffmpeg = if (Test-Path -LiteralPath $selected) { Get-Item -LiteralPath $selected } else { Get-ChildItem -LiteralPath $tools -Recurse -Filter 'ffmpeg.exe' -File -ErrorAction SilentlyContinue | Select-Object -First 1 }
if (!$DryRun -and !$ffmpeg) { throw "Missing FFmpeg under $tools" }
if ($ffmpeg) { $env:PATH = $ffmpeg.DirectoryName + ';' + $env:PATH }
$env:PIPER_VOICE_DIR = Join-Path $runtime 'models'
$env:PYTHONIOENCODING = 'utf-8'
$in = if ([IO.Path]::IsPathRooted($InputFile)) { $InputFile } else { Join-Path $root $InputFile }
if (!$OutputDir) { $OutputDir = Join-Path (Join-Path $runtime 'output') ('episode-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff')) }
$out = if ([IO.Path]::IsPathRooted($OutputDir)) { $OutputDir } else { Join-Path $root $OutputDir }
$argv = @((Join-Path $PSScriptRoot 'render_video.py'), '--input', $in, '--out', $out, '--voice', $Voice, '--encoder', $Encoder)
if ($DryRun) { $argv += '--dry-run' }
if ($AllowDemo) { $argv += '--allow-demo' }
if ($DemoSilence) { $argv += '--demo-silence' }
if ($AllowLonger) { $argv += '--allow-longer' }
Write-Output "PROJECT=$root"
Write-Output "RUNTIME=$runtime"
Write-Output "OUTPUT=$out"
$logDir = Join-Path $runtime 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ('run-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.txt')
Start-Transcript -Path $logFile -ErrorAction SilentlyContinue | Out-Null
& $python @argv
$result = $LASTEXITCODE
Stop-Transcript -ErrorAction SilentlyContinue | Out-Null
Write-Output "LOG=$logFile"
exit $result
