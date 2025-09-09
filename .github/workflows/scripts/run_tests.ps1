# Smoke test: импорт main из корня репозитория
$ErrorActionPreference = 'Stop'

# Python
$cmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $cmd) { Write-Error 'Python not found in PATH'; exit 1 }
$python = $cmd.Source

# Корень репо (текущая папка шага)
$repo = (Get-Location).Path

# Добавляем корень репо в PYTHONPATH (чтобы import main находился всегда)
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$repo;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $repo
}
$env:PYTHONIOENCODING = 'utf-8'

# Мини-скрипт, который просто импортит main
$py = @'
try:
    import main  # simple import smoke
    print("OK: imported main")
except Exception as e:
    print("FAIL: exception importing main:", e)
    raise
'@

# Пишем во временный файл и запускаем Питон из корня репо
$temp = [System.IO.Path]::Combine($env:TEMP, "smoke_test_main.py")
[System.IO.File]::WriteAllText($temp, $py, (New-Object System.Text.UTF8Encoding $false))
$proc = Start-Process -FilePath $python -WorkingDirectory $repo -ArgumentList $temp -NoNewWindow -Wait -PassThru
Remove-Item $temp -ErrorAction SilentlyContinue
exit $proc.ExitCode
