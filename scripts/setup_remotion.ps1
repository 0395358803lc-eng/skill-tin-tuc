# Copy portable Remotion sources into an isolated runtime, without touching unrelated files.
[CmdletBinding()]
param(
  [string]$Runtime='',
  [switch]$InstallPackages,
  [switch]$AllowSourceUpdate
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(!$Runtime){$Runtime=Join-Path (Split-Path -Parent $root) ((Split-Path $root -Leaf)+'-runtime')}
$Runtime=[IO.Path]::GetFullPath($Runtime)
$source=Join-Path $root 'remotion-template'
$target=Join-Path $Runtime 'remotion'
$inputs=@(
  (Join-Path $source 'package.json'),
  (Join-Path $source 'package-lock.json')
)
$inputs+=@(Get-ChildItem -LiteralPath (Join-Path $source 'src') -File | Select-Object -ExpandProperty FullName)
if($inputs.Count -lt 4){throw 'Remotion source or lock file missing'}
$copies=@()
foreach($src in $inputs){
  $relative=$src.Substring($source.Length).TrimStart('\')
  $dest=Join-Path $target $relative
  if(Test-Path -LiteralPath $dest){
    $old=(Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash
    $new=(Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
    if($old -eq $new){continue}
    if(!$AllowSourceUpdate){throw 'Will not overwrite different Remotion source without -AllowSourceUpdate: '+$dest}
  }
  $copies+=@([pscustomobject]@{src=$src;dest=$dest})
}
foreach($item in $copies){
  $parent=Split-Path -Parent $item.dest
  New-Item -ItemType Directory -Path $parent -Force |Out-Null
  Copy-Item -LiteralPath $item.src -Destination $item.dest -Force
}
if($InstallPackages){
  $npm=Get-Command npm.cmd -ErrorAction SilentlyContinue
  if(!$npm){throw 'npm.cmd not found. Install supported Node.js/npm before running -InstallPackages.'}
  Push-Location $target
  try{
    & $npm.Source ci --no-audit --no-fund
    if($LASTEXITCODE -ne 0){throw 'npm ci failed; runtime preserved for inspection'}
  }finally{Pop-Location}
}
if(!(Test-Path -LiteralPath (Join-Path $target 'node_modules\remotion'))){
  throw 'Remotion packages missing; run again with -InstallPackages'
}
Write-Output ('REMOTION_RUNTIME_READY='+$target)
