# ─── Run All Services Locally (Windows PowerShell) ───
# Usage: .\scripts\run_local.ps1
#
# This starts all 3 services in separate background jobs.
# Press Ctrl+C or run: Get-Job | Stop-Job; Get-Job | Remove-Job

Write-Host "=== EV Charging Optimization — Local Development ===" -ForegroundColor Cyan
Write-Host ""

$projectRoot = Split-Path $PSScriptRoot -Parent

# Check artifacts exist
$artifactsDir = Join-Path $projectRoot "ml-service\artifacts"
if (-not (Test-Path (Join-Path $artifactsDir "demand_model.pkl"))) {
    Write-Host "[ERROR] Models not trained yet. Run:" -ForegroundColor Red
    Write-Host "  cd ml-service" -ForegroundColor Yellow
    Write-Host "  python -m training.prepare_data --data-path ../data/acn_sessions.csv --output-dir artifacts/" -ForegroundColor Yellow
    Write-Host "  python -m training.train_demand --artifacts-dir artifacts/" -ForegroundColor Yellow
    Write-Host "  python -m training.train_departure --artifacts-dir artifacts/" -ForegroundColor Yellow
    exit 1
}

Write-Host "[1/3] Starting ML Service on port 8001..." -ForegroundColor Green
$mlJob = Start-Job -ScriptBlock {
    Set-Location $using:projectRoot\ml-service
    uvicorn app.main:app --host 127.0.0.1 --port 8001
}

Write-Host "[2/3] Starting Optimizer on port 8002..." -ForegroundColor Green
$optJob = Start-Job -ScriptBlock {
    Set-Location $using:projectRoot\optimizer
    uvicorn app.main:app --host 127.0.0.1 --port 8002
}

Start-Sleep -Seconds 3

Write-Host "[3/3] Starting Gateway on port 8000..." -ForegroundColor Green
$gwJob = Start-Job -ScriptBlock {
    $env:ML_SERVICE_URL = "http://127.0.0.1:8001"
    $env:OPTIMIZER_SERVICE_URL = "http://127.0.0.1:8002"
    Set-Location $using:projectRoot\gateway
    uvicorn app.main:app --host 127.0.0.1 --port 8000
}

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "=== All services started ===" -ForegroundColor Cyan
Write-Host "  API Gateway:  http://localhost:8000" -ForegroundColor White
Write-Host "  API Docs:     http://localhost:8000/docs" -ForegroundColor White
Write-Host "  ML Service:   http://localhost:8001" -ForegroundColor White
Write-Host "  Optimizer:    http://localhost:8002" -ForegroundColor White
Write-Host ""
Write-Host "  To start the dashboard, run in another terminal:" -ForegroundColor Yellow
Write-Host "    cd gateway; streamlit run dashboard/app.py --server.port 8501" -ForegroundColor Yellow
Write-Host ""
Write-Host "  To stop all services:" -ForegroundColor Yellow
Write-Host "    Get-Job | Stop-Job; Get-Job | Remove-Job" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Watching job output (Ctrl+C to stop watching)..." -ForegroundColor Gray

# Keep alive and show errors
try {
    while ($true) {
        foreach ($job in @($mlJob, $optJob, $gwJob)) {
            $output = Receive-Job $job -ErrorAction SilentlyContinue
            if ($output) { Write-Host $output }
        }
        Start-Sleep -Seconds 2
    }
}
finally {
    Write-Host "`nStopping services..." -ForegroundColor Yellow
    Get-Job | Stop-Job
    Get-Job | Remove-Job
    Write-Host "Done." -ForegroundColor Green
}
