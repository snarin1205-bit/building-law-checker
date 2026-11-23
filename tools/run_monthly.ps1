# 월간 법령·조례 점검 실행 래퍼 (Windows 작업 스케줄러용). 점검·자동 갱신 후 결과를 알림으로 띄운다.
# 수동 실행: powershell -File tools\run_monthly.ps1 [-DryRun]
param([switch]$DryRun)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = "utf-8"
$logDir = Join-Path $env:LOCALAPPDATA "law-checker\monthly"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("run-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

$args2 = @("tools/monthly_update.py")
if ($DryRun) { $args2 += "--dry-run" }
& python @args2 *>&1 | Tee-Object -FilePath $log | Out-Null
$code = $LASTEXITCODE

$msg = if ($code -eq 0) { "변경 없음 또는 자동 갱신 완료" } else { "수동 확인이 필요한 항목이 있습니다 — 보고서 확인" }
try {
    Add-Type -AssemblyName System.Windows.Forms
    $n = New-Object System.Windows.Forms.NotifyIcon
    $n.Icon = [System.Drawing.SystemIcons]::Information
    $n.Visible = $true
    $n.ShowBalloonTip(15000, "건축법규 데이터 월간 점검", $msg, [System.Windows.Forms.ToolTipIcon]::Info)
    Start-Sleep -Seconds 16
    $n.Dispose()
} catch {}
exit $code
