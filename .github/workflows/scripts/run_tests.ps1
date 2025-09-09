# Smoke test: simple "import main" in PowerShell
$python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $python) { Write-Error "Python not found in PATH"; exit 1 }

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
