# Portable Windows bootstrap. -CheckOnly is strictly read-only.
[CmdletBinding()]
param(
  [string]$Runtime='',
  [string]$FFmpegSource='',
  [string]$VoiceModelsSource='',
  [switch]$AcceptExistingRuntime,
  [switch]$SkipDependencies,
  [switch]$CheckOnly
)
$ErrorActionPreference='Stop'
$skill=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
if(!$Runtime){$Runtime="$skill-runtime"}
$Runtime=[IO.Path]::GetFullPath($Runtime)
if($Runtime.TrimEnd('\') -eq [IO.Path]::GetPathRoot($Runtime).TrimEnd('\')){
  throw 'Runtime cannot be a drive root'
}
$skillBase=$skill.TrimEnd('\')+'\'
$runtimeBase=$Runtime.TrimEnd('\')+'\'
if($Runtime.TrimEnd('\') -eq $skill.TrimEnd('\')){throw 'Runtime must never be inside the Skill source folder'}
if($runtimeBase.StartsWith($skillBase,[StringComparison]::OrdinalIgnoreCase)){
  throw 'Runtime cannot be nested inside Skill'
}
if($skillBase.StartsWith($runtimeBase,[StringComparison]::OrdinalIgnoreCase)){
  throw 'Runtime must not be parent of Skill'
}
$existing=@()
if(Test-Path -LiteralPath $Runtime){
  $existing=@(Get-ChildItem -LiteralPath $Runtime -Force -ErrorAction Stop |Select-Object -First 1)
}
$runtimeSafe=($existing.Count -eq 0 -or $AcceptExistingRuntime.IsPresent)
$pyCmd=Get-Command py.exe -ErrorAction SilentlyContinue
$venv=Join-Path $Runtime '.venv\Scripts\python.exe'
$pythonSystem=$false
$pyVersion=''
if($pyCmd){
  $pyVersion=(& $pyCmd.Source -3.13 --version 2>&1 |Out-String).Trim()
  $pythonSystem=($LASTEXITCODE -eq 0 -and $pyVersion -match 'Python 3\.13')
}
$pythonAvailable=$pythonSystem -or (Test-Path -LiteralPath $venv)
$nodeOk=$null -ne (Get-Command node.exe -ErrorAction SilentlyContinue)
$npmOk=$null -ne (Get-Command npm.cmd -ErrorAction SilentlyContinue)
$browser=$null
$browserOverride=if($env:NEWS_CHROME_PATH){$env:NEWS_CHROME_PATH}else{$env:REMOTION_BROWSER_EXECUTABLE}
if($browserOverride){
  if(Test-Path -LiteralPath $browserOverride -PathType Leaf){$browser=[IO.Path]::GetFullPath($browserOverride)}
}else{
  foreach($name in @('chrome.exe','chromium.exe','chrome','chromium')){
    $command=Get-Command $name -ErrorAction SilentlyContinue
    if($command -and $command.Source -and (Test-Path -LiteralPath $command.Source -PathType Leaf)){$browser=$command.Source;break}
  }
  if(!$browser){
    foreach($base in @($env:ProgramFiles,[Environment]::GetEnvironmentVariable('ProgramFiles(x86)'),$env:LOCALAPPDATA)){
      if(!$base){continue}
      foreach($sub in @('Google\Chrome\Application\chrome.exe','Chromium\Application\chrome.exe','Chromium\Application\chromium.exe')){
        $candidate=Join-Path $base $sub
        if(Test-Path -LiteralPath $candidate -PathType Leaf){$browser=$candidate;break}
      }
      if($browser){break}
    }
  }
}
$ffmpegFolder=if($FFmpegSource){$FFmpegSource}else{Join-Path $Runtime 'tools\ffmpeg-selected'}
$ffmpegReady=((Test-Path -LiteralPath (Join-Path $ffmpegFolder 'ffmpeg.exe') -PathType Leaf) -and
              (Test-Path -LiteralPath (Join-Path $ffmpegFolder 'ffprobe.exe') -PathType Leaf))
if(!$ffmpegReady -and !$FFmpegSource){
  if((Get-Command ffmpeg.exe -ErrorAction SilentlyContinue) -and (Get-Command ffprobe.exe -ErrorAction SilentlyContinue)){$ffmpegReady=$true}
}
$voiceFolder=if($VoiceModelsSource){$VoiceModelsSource}else{Join-Path $Runtime 'models'}
$voiceReady=$true
foreach($voice in @('vi_VN-vais1000-medium','en_US-lessac-medium')){
  if(!(Test-Path -LiteralPath (Join-Path $voiceFolder ($voice+'.onnx')) -PathType Leaf) -or
     !(Test-Path -LiteralPath (Join-Path $voiceFolder ($voice+'.onnx.json')) -PathType Leaf)){
    $voiceReady=$false
  }
}
$check=[ordered]@{
  skill=$skill; runtime=$Runtime
  mode=if($CheckOnly){'CHECK_ONLY_NO_MUTATION'}else{'INSTALL'}
  runtime_safe=$runtimeSafe; python_313=$pythonAvailable; python_version=$pyVersion
  node=$nodeOk; npm=$npmOk; chrome=[bool]$browser; chrome_path=$browser
  ffmpeg_and_ffprobe=$ffmpegReady; piper_vi_en_models=$voiceReady
  deps_install_skipped=[bool]$SkipDependencies
}
$missing=@()
foreach($name in @('runtime_safe','python_313','node','npm','chrome','ffmpeg_and_ffprobe','piper_vi_en_models')){
  if(!$check[$name]){$missing+=$name}
}
$check['missing']=$missing
$check['preflight_pass']=($missing.Count -eq 0)
$check | ConvertTo-Json -Depth 5
if($CheckOnly){if($missing.Count){exit 2};exit 0}
if($missing.Count){throw ('Prerequisites missing; no files changed: '+($missing -join ', ')+'. Run -CheckOnly and supply licensed FFmpeg/Piper sources.')}
# Mutations begin only after preflight passes.
New-Item -ItemType Directory -Path $Runtime -Force |Out-Null
if(!(Test-Path -LiteralPath $venv)){
  & $pyCmd.Source -3.13 -m venv (Join-Path $Runtime '.venv')
  if($LASTEXITCODE -ne 0){throw 'Python isolated venv setup failed'}
}
if(!$SkipDependencies){
  & $venv -m pip install --disable-pip-version-check -r (Join-Path $skill 'requirements-smart-crop.txt')
  if($LASTEXITCODE -ne 0){throw 'pip installation failed; retained runtime for investigation'}
  & (Join-Path $PSScriptRoot 'setup_remotion.ps1') -Runtime $Runtime -InstallPackages -AllowSourceUpdate:$AcceptExistingRuntime
  if($LASTEXITCODE -ne 0){throw 'npm/Remotion installation failed; retained runtime for investigation'}
}
function CopyLicensedAssets([string]$source,[string]$relative){
  if(!$source){return}
  if(!(Test-Path -LiteralPath $source -PathType Container)){throw 'Supplied asset folder missing: '+$source}
  $target=Join-Path $Runtime $relative
  New-Item -ItemType Directory -Path $target -Force |Out-Null
  $allowed=if($relative -eq 'models'){
    @('vi_VN-vais1000-medium.onnx','vi_VN-vais1000-medium.onnx.json',
      'en_US-lessac-medium.onnx','en_US-lessac-medium.onnx.json')
  }else{@('ffmpeg.exe','ffprobe.exe')}
  foreach($file in $allowed){
    $src=Join-Path $source $file
    if(!(Test-Path -LiteralPath $src -PathType Leaf)){throw 'Required licensed asset missing: '+$file}
    $dest=Join-Path $target $file
    if(Test-Path -LiteralPath $dest){
      if((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash -eq
         (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash){continue}
      throw 'Will not replace existing dependency file: '+$dest
    }
    Copy-Item -LiteralPath $src -Destination $dest
  }
}
CopyLicensedAssets $FFmpegSource 'tools\ffmpeg-selected'
CopyLicensedAssets $VoiceModelsSource 'models'
$env:NEWS_SKILL_RUNTIME=$Runtime
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PATH=(Join-Path $Runtime 'tools\ffmpeg-selected')+';'+$env:PATH
& $venv -B (Join-Path $PSScriptRoot 'doctor.py') --runtime $Runtime
if($LASTEXITCODE -ne 0){throw 'Doctor did not confirm a working dual-aspect pipeline. Retained runtime for inspection.'}
& $venv -B -m unittest discover -s (Join-Path $skill 'tests') -q
if($LASTEXITCODE -ne 0){throw 'Post-install unit tests failed'}
Write-Output 'SKILL_WINDOWS_BOOTSTRAP_PASS; manual publication only'
