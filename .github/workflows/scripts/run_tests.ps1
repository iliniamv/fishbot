# Deploy & restart service (Windows PowerShell 5.1)
$ErrorActionPreference = 'Stop'

$proj    = $env:FISHBOT_PROJECT_DIR
$service = $env:FISHBOT_SERVICE_NAME
if (-not $proj)    { throw "FISHBOT_PROJECT_DIR is empty" }
if (-not $service) { throw "FISHBOT_SERVICE_NAME is empty" }

Write-Host "Deploying to $proj, service $service"

# Создаём папку, если её нет
if (-not (Test-Path $proj)) { New-Item -ItemType Directory -Force -Path $proj | Out-Null }

# Останавливаем службу (если запущена)
try {
    $svc = Get-Service -Name $service -ErrorAction Stop
    if ($svc.Status -ne 'Stopped') {
        Write-Host "Stopping service $service..."
        Stop-Service -Name $service -Force -ErrorAction Stop
        Start-Sleep -Seconds 2
    }
} catch {
    Write-Warning "Could not stop service $service (it may not be running). $_"
}

# Копируем файлы из текущего репо в папку проекта
$src    = (Get-Location).Path
$robolog = Join-Path $env:TEMP "robocopy_fishbot.log"
$opts = @(
    '/MIR','/FFT','/R:2','/W:2','/NP','/NFL','/NDL','/NJH','/NJS',
    '/XD','.git','.github','__pycache__','.venv'
)
& robocopy $src $proj *.* $opts /LOG:$robolog
$rc = $LASTEXITCODE
Write-Host "Robocopy exit code: $rc"

# Robocopy: 0..7 = SUCCESS
if ($rc -gt 7) {
    Write-Host "---- ROBOCOPY LOG ----"
    Get-Content $robolog | Write-Host
    throw "Robocopy failed with code $rc"
}

# Запускаем службу
try {
    Write-Host "Starting service $service..."
    Start-Service -Name $service -ErrorAction Stop
} catch {
    Write-Warning "Start-Service failed. Trying 'sc start'..."
    & sc.exe start $service | Out-Null
}

Write-Host "Deploy finished."
exit 0
