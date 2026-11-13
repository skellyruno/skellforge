# Skelly VST3 / GUI profiling helper for user-controlled FL Studio sessions.
# READ-ONLY: queries process CPU time; never starts/stops FL Studio, changes
# audio, edits FLPs, installs VST3s or modifies project state.
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Baseline","NativeClosed","NativeOpen","JuceClosed","JuceOpen")]
    [string]$Scenario,
    [string]$ProcessName="FL64",
    [ValidateRange(5,300)]
    [int]$Seconds=30,
    [ValidateRange(100,2000)]
    [int]$SampleMilliseconds=500,
    [string]$OutputPath=""
)
$ErrorActionPreference="Stop"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $desktop=[Environment]::GetFolderPath("Desktop")
    if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path $desktop)) {
        $desktop=(Get-Location).Path
    }
    $OutputPath=Join-Path $desktop "SkellNative_FLStudio_Process_CPU.csv"
}
$matches=@(Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
if ($matches.Count -ne 1) {
    throw ("Expected exactly one running FL Studio process named '$ProcessName'; " +
           "found $($matches.Count). Open FL Studio, or run with -ProcessName " +
           "set to the name shown by Get-Process.")
}
$process=$matches[0]
$coreCount=[Environment]::ProcessorCount
if($coreCount -lt 1) { throw "Unable to determine logical processor count" }
$timestamp=Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
$watch=[System.Diagnostics.Stopwatch]::StartNew()
$prevWall=0.0
$prevCpu=$process.TotalProcessorTime.TotalMilliseconds
$intervals=New-Object 'System.Collections.Generic.List[double]'
Write-Host "READ ONLY: recording FL Studio PROCESS CPU for '$Scenario'"
Write-Host "Process: $($process.ProcessName) (PID $($process.Id)), logical CPUs: $coreCount"
Write-Host "This is total process CPU (normalized by all logical cores), NOT plugin-only CPU."
while($watch.Elapsed.TotalSeconds -lt $Seconds) {
    Start-Sleep -Milliseconds $SampleMilliseconds
    $watch.Stop()
    $wall=$watch.Elapsed.TotalMilliseconds
    $watch.Start()
    try {
        $process.Refresh()
        if($process.HasExited) { throw "FL Studio closed during sample" }
        $cpu=$process.TotalProcessorTime.TotalMilliseconds
    } catch {
        throw "Could not sample FL Studio process: $_"
    }
    $deltaWall=$wall-$prevWall
    $deltaCpu=$cpu-$prevCpu
    if($deltaWall -gt 0 -and $deltaCpu -ge 0) {
        $percent=100.0*$deltaCpu/($deltaWall*$coreCount)
        if([double]::IsFinite($percent)) { [void]$intervals.Add($percent) }
    }
    $prevWall=$wall
    $prevCpu=$cpu
}
$watch.Stop()
if($intervals.Count -lt 2) { throw "Not enough valid CPU samples" }
$sorted=@($intervals | Sort-Object)
$median=($sorted[[int][math]::Floor(($sorted.Count-1)/2)] +
         $sorted[[int][math]::Floor($sorted.Count/2)])/2.0
$mean=($intervals | Measure-Object -Average).Average
$maximum=($intervals | Measure-Object -Maximum).Maximum
$row=[PSCustomObject]@{
    RecordedAt=$timestamp
    Scenario=$Scenario
    ProcessName=$process.ProcessName
    ProcessId=$process.Id
    Seconds=[math]::Round($watch.Elapsed.TotalSeconds,2)
    Samples=$intervals.Count
    LogicalCPUs=$coreCount
    MedianProcessCPU=[math]::Round($median,3)
    MeanProcessCPU=[math]::Round($mean,3)
    MaxProcessCPU=[math]::Round($maximum,3)
}
if(Test-Path -LiteralPath $OutputPath) {
    $row | Export-Csv -Path $OutputPath -Append -NoTypeInformation
} else {
    $row | Export-Csv -Path $OutputPath -NoTypeInformation
}
$row | Format-List
Write-Host "Saved: $OutputPath"
Write-Host "Compare scenarios in the SAME FLP/audio/buffer setup."
Write-Host "The values include the entire FL Studio process, not per-plugin DSP or UI."
