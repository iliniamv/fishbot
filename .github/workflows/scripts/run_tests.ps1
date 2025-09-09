# Deploy & restart service (Windows PowerShell 5.1)
$ErrorActionPreference = 'Continue'

$proj    = $env:FISHBOT_PROJECT_DIR
$service = $env:FISHBOT_SERVICE_NAME
if (-not $proj)    { Write-Error "FISHBOT_PROJECT_DIR is empty"; exit 1 }
if (-not $service) { Write-Error "FISHBOT_SERVICE_NAME is empty"; exit 1 }

Write-Host "Deploying to $proj, service $service"

# Создаём папку, если её нет
if (-not (Test-Path $proj)) { New-Item -ItemType Directory -Force -Path $proj | Out-Null }

# Копируем файлы
$src    = (Get-Location).Path
$opts = @(
    '/MIR','/FFT','/R:2','/W:2','/NP','/NFL','/NDL','/NJH','/NJS',
    '/XD','.git','.github','__pycache__','.venv'
)
& robocopy $src $proj *.* $opts
$rc = $LASTEXITCODE
Write-Host "Robocopy exit code: $rc"

# Robocopy: 0..7 = SUCCESS
if ($rc -gt 7) {
    Write-Error "Robocopy failed with code $rc"
    exit 1
}

# Остановка и запуск службы (если есть)
try {
    $svc = Get-Service -Name $service -ErrorAction Stop
    if ($svc.Status -ne 'Stopped') {
        Write-Host "Stopping service $service..."
        Stop-Service -Name $service -Force -ErrorAction Stop
    }
    Start-Sleep -Seconds 2
    Write-Host "Starting service $service..."
    Start-Service -Name $service -ErrorAction Stop
} catch {
    Write-Warning "Service $service not found or could not be restarted. Please check manually."
}

Write-Host "Deploy finished."
exit 0
