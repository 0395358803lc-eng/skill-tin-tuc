param(
[Parameter(Mandatory=$true)][string]$InputFile,
[string]$OutputDir='',
[ValidateSet('auto','cpu','nvenc')][string]$Encoder='auto',
[ValidateSet('9:16','16:9','both')][string]$Aspect='',
[string]$Voice='',
[ValidateRange(0.75,1.35)][double]$SpeechRate=1.0,
[string]$Lexicon='',
[switch]$AllowDemo,
[switch]$DemoSilence,
[switch]$DryRun,
[switch]$AllowLonger,
[string]$Music=''
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$runtime=if($env:NEWS_SKILL_RUNTIME){$env:NEWS_SKILL_RUNTIME}else{Join-Path (Split-Path -Parent $root) ((Split-Path $root -Leaf)+'-runtime')}
$python=Join-Path $runtime '.venv\Scripts\python.exe'
$ffmpeg=Join-Path $runtime 'tools\ffmpeg-selected\ffmpeg.exe'
if(!(Test-Path -LiteralPath $python)){throw 'Missing Python runtime'}
if(!(Test-Path -LiteralPath $ffmpeg)){
  $found=Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
  if($found){$ffmpeg=$found.Source}
}
if(!$DryRun -and !(Test-Path -LiteralPath $ffmpeg)){throw 'FFmpeg missing in runtime or PATH'}
if(Test-Path -LiteralPath $ffmpeg){$env:PATH=(Split-Path $ffmpeg -Parent)+';'+$env:PATH}
$env:PIPER_VOICE_DIR=Join-Path $runtime 'models'
$env:NEWS_SKILL_RUNTIME=$runtime
$env:PYTHONIOENCODING='utf-8'
$source=if([IO.Path]::IsPathRooted($InputFile)){$InputFile}else{Join-Path $root $InputFile}
if(!$OutputDir){$OutputDir=Join-Path (Join-Path $runtime 'output') ('episode-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff'))}
$destination=if([IO.Path]::IsPathRooted($OutputDir)){$OutputDir}else{Join-Path $root $OutputDir}
$argv=@((Join-Path $PSScriptRoot 'video_pipeline.py'),'--input',$source,'--out',$destination,'--encoder',$Encoder)
if($Voice){$argv+=@('--voice',$Voice)}
$argv+=@('--speech-rate',($SpeechRate.ToString([cultureinfo]::InvariantCulture)))
if($Lexicon){$argv+=@('--lexicon',$Lexicon)}
if($Aspect){$argv+=@('--aspect',$Aspect)}
if($AllowDemo){$argv+='--allow-demo'}
if($DemoSilence){$argv+='--demo-silence'}
if($DryRun){$argv+='--dry-run'}
if($AllowLonger){$argv+='--allow-longer'}
if($Music){$argv+=@('--music',$Music)}
Write-Output ('SKILL='+$root)
Write-Output ('OUTPUT='+$destination)
$logs=Join-Path $runtime 'logs';New-Item -ItemType Directory -Force $logs|Out-Null
$transcript=Join-Path $logs ('stage3-'+(Get-Date -Format 'yyyyMMdd-HHmmss-fff')+'.txt')
Start-Transcript -Path $transcript -ErrorAction SilentlyContinue|Out-Null
& $python @argv
$rc=$LASTEXITCODE
Stop-Transcript -ErrorAction SilentlyContinue|Out-Null
Write-Output ('LOG='+$transcript)
exit $rc
