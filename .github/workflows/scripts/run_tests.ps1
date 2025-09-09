# Smoke test for Windows PowerShell 5.1
# Запускаем python из КОРНЯ РЕПО, чтобы import main сработал.

$cmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $cmd) { Write-Error "Python not found in PATH"; exit 1 }
$python = $cmd.Source

$repo = (Get-Location).Path

$py = @'
try:
    import main  # simple import smoke
    print("OK: imported main")
except Exception as e:
    print("FAIL: exception importing main:", e)
    raise
'@

$temp = [System.IO.Path]::Combine($env:TEMP, "smoke_test_main.py")
$py | Out-File -FilePath $temp -Encoding ASCII -Force

# Ключевое: запускаем python в рабочей директории репо
$proc = Start-Process -FilePath $python -WorkingDirectory $repo -ArgumentList $temp -NoNewWindow -Wait -PassThru

Remove-Item $temp -ErrorAction SilentlyContinue
exit $proc.ExitCode
