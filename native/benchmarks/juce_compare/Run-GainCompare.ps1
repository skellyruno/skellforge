param([string]$JucePath="",[string]$OutputPath="")
$ErrorActionPreference="Stop"
$root=$PSScriptRoot
$build=Join-Path $root "build"
if(-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    throw "CMake missing: install Visual Studio C++ and CMake."
}
$argsConfigure=@("-S",$root,"-B",$build,"-A","x64")
if($JucePath -ne "") {
    $path=(Resolve-Path $JucePath).Path
    $argsConfigure+="-DJUCE_PATH=$path"
}
& cmake @argsConfigure
if($LASTEXITCODE -ne 0) { throw "CMake configuration failed" }
& cmake --build $build --target SkellGainCompare --config Release --parallel 2
if($LASTEXITCODE -ne 0) { throw "Benchmark compilation failed" }
$exe=Join-Path $build "Release/SkellGainCompare.exe"
if(-not (Test-Path $exe)) { throw "Compiled benchmark missing" }
if($OutputPath -eq "") {
    $dest=Join-Path $env:USERPROFILE "Desktop"
    if(-not (Test-Path $dest)) { $dest=(Get-Location).Path }
    $OutputPath=Join-Path $dest "SkellNative_JUCE_Gain_Comparison.csv"
}
& $exe | Set-Content -LiteralPath $OutputPath -Encoding UTF8
if($LASTEXITCODE -ne 0) { throw "Audio parity check or benchmark failed" }
$rows=Import-Csv -LiteralPath $OutputPath
if($rows.Count -ne 9) { throw "Expected nine rate/buffer results" }
$rows | Format-Table -AutoSize
Write-Host "Saved benchmark results: $OutputPath"
Write-Host "DSP-only timings, NOT measured FL Studio CPU usage."
