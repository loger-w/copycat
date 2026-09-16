param(
    [Parameter(Mandatory = $true)][string]$CliArgs,
    [Parameter(Mandatory = $true)][string]$Label
)
# worktree 根跑 `python -m copycat <CliArgs>`:印 exit code / 耗時 / 峰值 working set / stdout / stderr
$py = "C:\side-project\copycat\.venv\Scripts\python.exe"
$wt = "C:\side-project\copycat\.claude\worktrees\fix-pr-275-review-followups"
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $py
$psi.Arguments = "-m copycat $CliArgs"
$psi.WorkingDirectory = $wt
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$psi.EnvironmentVariables["PYTHONUTF8"] = "1"
$psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
$psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$p = [System.Diagnostics.Process]::Start($psi)
$out = $p.StandardOutput.ReadToEndAsync()
$err = $p.StandardError.ReadToEndAsync()
$peak = 0
while (-not $p.HasExited) {
    # venv 的 python.exe 是 launcher,真正跑的是它的子行程(base interpreter):量子行程的峰值
    $ids = @($p.Id) + @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($p.Id)" -ErrorAction SilentlyContinue | ForEach-Object { $_.ProcessId })
    foreach ($id in $ids) {
        $gp = Get-Process -Id $id -ErrorAction SilentlyContinue
        if ($gp -and $gp.PeakWorkingSet64 -gt $peak) { $peak = $gp.PeakWorkingSet64 }
    }
    Start-Sleep -Milliseconds 250
}
$p.WaitForExit()
$sw.Stop()
"=== $Label"
"cmd: python -m copycat $CliArgs"
"exit: $($p.ExitCode)  elapsed: $([math]::Round($sw.Elapsed.TotalSeconds, 1)) s  peak_ws: $([math]::Round($peak / 1GB, 2)) GB"
"--- stdout"
$out.Result.TrimEnd()
"--- stderr"
$err.Result.TrimEnd()
""
