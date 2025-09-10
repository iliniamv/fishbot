# Smoke test for Windows PowerShell 5.1
# Проверяем, что main.py импортируется из корня репозитория.

$ErrorActionPreference = 'Stop'

$cmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $cmd) { Write-Error 'Python not found in PATH'; exit 1 }
$python = $cmd.Source

# Корень репозитория = текущая рабочая директория job
$repo = (Get-Location).Path

# Подстрахуем PYTHONPATH
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$repo;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $repo
}
$env:PYTHONIOENCODING = 'utf-8'

# Пишем мини-скрипт во временный файл (без проблем с отступами)
$py = @'
try:
    import main  # simple import smoke
    print("OK: imported main")
except Exception as e:
    print("FAIL: exception importing main:", e)
    raise
'@

$temp = [System.IO.Path]::Combine($env:TEMP, "smoke_test_main.py")
[System.IO.File]::WriteAllText($temp, $py, (New-Object System.Text.UTF8Encoding $false))

# ВАЖНО: запускаем из корня репозитория
$proc = Start-Process -FilePath $python -WorkingDirectory $repo -ArgumentList $temp -NoNewWindow -Wait -PassThru

Remove-Item $temp -ErrorAction SilentlyContinue
exit $proc.ExitCode
