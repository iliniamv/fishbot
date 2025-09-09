Param()

# Requires env vars set as GitHub Secrets and exposed to job env
$projectDir = $env:FISHBOT_PROJECT_DIR
$service    = $env:FISHBOT_SERVICE_NAME

if (-not $projectDir) { Write-Error "FISHBOT_PROJECT_DIR is empty"; exit 1 }
if (-not $service)    { Write-Error "FISHBOT_SERVICE_NAME is empty"; exit 1 }

Write-Host "Deploying to $projectDir, service $service"

# Ensure target dir exists
if (!(Test-Path $projectDir)) {
  New-Item -ItemType Directory -Force -Path $projectDir | Out-Null
}

# Stop service if exists (ignore errors)
try {
  Stop-Service -Name $service -ErrorAction Stop
  Write-Host "Stopped service $service"
} catch {
  Write-Warning "Could not stop service $service (it may not be running)."
}

# Mirror workspace to project dir, excluding dev folders
$src = (Resolve-Path "$PSScriptRoot\..").Path  # repo root
$rc = & robocopy $src $projectDir /MIR /NFL /NDL /NJH /NJS /NP /XD ".git" ".github" "venv" "__pycache__" ".pytest_cache" "logs"
$ec = $LASTEXITCODE
Write-Host "Robocopy exit code: $ec"

# Start service (or try to create via sc if it's missing)
try {
  Start-Service -Name $service -ErrorAction Stop
  Write-Host "Started service $service"
} catch {
  Write-Warning "Start-Service failed. Trying 'sc start'..."
  sc.exe start $service | Out-Null
}

Write-Host "Deploy finished."
