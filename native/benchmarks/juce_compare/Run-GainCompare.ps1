param([string]$JucePath="",[string]$OutputPath="")
$ErrorActionPreference="Stop"
$root=$PSScriptRoot
$build=Join-Path $root "build"
# Visual Studio may include CMake without adding it to normal PowerShell's PATH.
# Locate an existing executable first; do not assume the software is absent.
function Find-CMake {
    $onPath = Get-Command cmake.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    $candidates = @()
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles 'CMake\bin\cmake.exe'
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} 'CMake\bin\cmake.exe'
    }
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA 'Programs\CMake\bin\cmake.exe'
    }

    # Visual Studio edition paths are discovered via the official installer.
    $vswherePaths = @()
    if (${env:ProgramFiles(x86)}) {
        $vswherePaths += Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    }
    if ($env:ProgramFiles) {
        $vswherePaths += Join-Path $env:ProgramFiles 'Microsoft Visual Studio\Installer\vswhere.exe'
    }
    foreach ($vswhere in $vswherePaths) {
        if (-not (Test-Path -LiteralPath $vswhere -PathType Leaf)) { continue }
        $installations = @(& $vswhere -products '*' -property installationPath 2>$null)
        foreach ($installation in $installations) {
            if ([string]::IsNullOrWhiteSpace($installation)) { continue }
            $candidates += Join-Path $installation 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
        }
    }
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

$cmake = Find-CMake
if (-not $cmake) {
    throw ("CMake executable not found in PATH or known Visual Studio locations. " +
           "Open Developer PowerShell for Visual Studio and try 'cmake --version'. " +
           "If still missing, check Visual Studio Installer > Modify > " +
           "Individual components > C++ CMake tools for Windows, or install CMake.")
}
Write-Host "Using CMake: $cmake"
& $cmake --version
if ($LASTEXITCODE -ne 0) { throw "Located CMake cannot execute" }
$argsConfigure=@("-S",$root,"-B",$build,"-A","x64")
if($JucePath -ne "") {
    $path=(Resolve-Path $JucePath).Path
    $argsConfigure+="-DJUCE_PATH=$path"
}
& $cmake @argsConfigure
if($LASTEXITCODE -ne 0) { throw "CMake configuration failed" }
& $cmake --build $build --target SkellGainCompare --config Release --parallel 2
if($LASTEXITCODE -ne 0) { throw "Benchmark compilation failed" }
$matching=@(Get-ChildItem -Path $build -Filter "SkellGainCompare.exe" -File -Recurse)
if($matching.Count -ne 1) { throw "Expected one compiled SkellGainCompare.exe; found $($matching.Count)" }
$exe=$matching[0].FullName
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
