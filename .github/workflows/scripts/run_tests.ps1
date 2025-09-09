# Smoke test for Windows PowerShell 5.1 — import main from repo root

$cmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $cmd) { Write-Error "Python not found in PATH"; exit 1 }
$python = $cmd.Source

# Текущая папка шага — корень репозитория
$repo = (Get-Location).Path

$code = @"
import sys, os
sys.path.insert(0, r"$repo")
try:
    import main  # must be in repo root
    print("OK: imported main")
except Exception as e:
    print("FAIL: exception importing main:", e)
    raise
"@

$proc = Start-Process -FilePath $python -ArgumentList @("-c", $code) -NoNewWindow -Wait -PassThru
exit $proc.ExitCode
