# Deploy & (мягкий) рестарт службы для Windows PowerShell 5.1
# - Robocopy коды 0..7 считаем успехом
# - Ошибки управления службой НЕ валят job (warning), в конце exit 0

$ErrorActionPreference = 'Continue'

$proj    = $env:FISHBOT_PROJECT_DIR
$service = $env:FISHBOT_SERVICE_NAME
if (-not $proj)    { Write-Error "FISHBOT_PROJECT_DIR is empty"; exit 1 }
if (-not $service) { Write-Error "FISHBOT_SERVICE_NAME is empty"; exit 1 }

Write-Host "Deploying to $proj, service $service"

# Гарантируем каталог назначения
if (-not (Test-Path $proj)) { New-Item -ItemType Directory -Force -Path $proj | Out-Null }

# Путь исходников = корень чекаута
$src = (Get-Location).Path

# Останавливаем службу (если есть)
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

# Копируем файлы
$opts = @(
    '/MIR','/FFT','/R:2','/W:2','/NP','/NFL','/NDL','/NJH','/NJS',
    '/XD','.git','.github','__pycache__','.venv','.pytest_cache','logs'
)
& robocopy $src $proj *.* $opts
$rc = $LASTEXITCODE
Write-Host "Robocopy exit code: $rc"

# Robocopy: 0..7 = SUCCESS
if ($rc -gt 7) {
    Write-Error "Robocopy failed with code $rc"
    exit 1
}

# Запускаем службу (мягко)
try {
    Write-Host "Starting service $service..."
    Start-Service -Name $service -ErrorAction Stop
} catch {
    Write-Warning "Start-Service failed. Trying 'sc start'..."
    try {
        & sc.exe start $service | Out-Null
    } catch {
        Write-Warning "Service $service not found or could not be started."
    }
}

Write-Host "Deploy finished."
exit 0
