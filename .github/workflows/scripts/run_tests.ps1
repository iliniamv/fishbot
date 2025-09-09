# Smoke test: simple "import main" for Windows PowerShell 5.1
$cmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $cmd) { Write-Error "Python not found in PATH"; exit 1 }
$python = $cmd.Source

$code = @"
try:
    import importlib
    import main  # simple import smoke
    print("OK: imported main")
except Exception as e:
    print("FAIL: exception importing main:", e)
    raise
"@

$env:PYTHONIOENCODING = 'utf-8'
$proc = Start-Process -FilePath $python -ArgumentList @("-c", $code) -NoNewWindow -Wait -PassThru
exit $proc.ExitCode
