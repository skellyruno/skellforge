param([string]$SDKPath="",[string]$OutputPath="")
$ErrorActionPreference="Stop"
$root=Split-Path -Parent $PSScriptRoot
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
if($SDKPath -ne "") {
    $path=(Resolve-Path $SDKPath).Path
    $argsConfigure+="-DSKELLNATIVE_STEINBERG_SDK=$path"
}
& $cmake @argsConfigure
if($LASTEXITCODE -ne 0) { throw "CMake configuration failed" }
& $cmake --build $build --target SkellNativeVst3AdapterBench --config Release --parallel 2
if($LASTEXITCODE -ne 0) { throw "Benchmark compilation failed" }
$matching=@(Get-ChildItem -Path $build -Filter "SkellNativeVst3AdapterBench.exe" -File -Recurse)
if($matching.Count -ne 1) { throw "Expected one compiled SkellNativeVst3AdapterBench.exe; found $($matching.Count)" }
$exe=$matching[0].FullName
if($OutputPath -eq "") {
    $dest=Join-Path $env:USERPROFILE "Desktop"
    if(-not (Test-Path $dest)) { $dest=(Get-Location).Path }
    $OutputPath=Join-Path $dest "SkellNative_VST3_Adapter_Local.csv"
}
$result=@(& $exe)
if($LASTEXITCODE -ne 0) { throw "VST3 adapter parity or benchmark failed" }
# Ignore two explanatory preface lines from the executable; output clean CSV.
$csv=@($result | Where-Object { $_ -match '^(rate_hz,|[0-9]{5},)' })
$csv | Set-Content -LiteralPath $OutputPath -Encoding UTF8
$rows=@(Import-Csv -LiteralPath $OutputPath)
if($rows.Count -ne 72) { throw "Expected 72 VST3 rate/format/automation/meter results" }
$rows | Select-Object -First 12 | Format-Table -AutoSize
Write-Host "Saved 72-row adapter benchmark: $OutputPath"
Write-Host "Actual SkellNative VST3 process() timing, NOT whole FL Studio/ASIO CPU load."
