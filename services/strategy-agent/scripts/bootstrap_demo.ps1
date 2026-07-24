param(
    [string]$PythonPath = "C:\Python314\python.exe",
    [switch]$Force
)

$serviceDir = Split-Path -Parent $PSScriptRoot
$artifactDir = Join-Path $serviceDir "artifacts\historical_modeling_v2"
$pdArtifactDir = Join-Path $serviceDir "artifacts\pd_risk_model"
$requiredArtifacts = @(
    "open_model.joblib",
    "click_model.joblib",
    "conversion_model.joblib",
    "unsubscribe_model.joblib"
)

if (-not (Test-Path $PythonPath)) {
    throw "Python was not found at: $PythonPath"
}

$missingArtifacts = $requiredArtifacts | Where-Object {
    -not (Test-Path (Join-Path $artifactDir $_))
}

if ($Force -or $missingArtifacts) {
    Write-Host "Building historical response model artifacts..."
    Push-Location $serviceDir
    try {
        & $PythonPath "scripts\train_historical_response_models.py" "--output-dir" "artifacts\historical_modeling_v2"
        if ($LASTEXITCODE -ne 0) {
            throw "Model training failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "Historical response model artifacts are ready."
}

$pdArtifact = Join-Path $pdArtifactDir "pd_6m_model.joblib"
if ($Force -or -not (Test-Path $pdArtifact)) {
    Write-Host "Building PD risk model artifact..."
    Push-Location $serviceDir
    try {
        & $PythonPath "scripts\train_pd_risk_model.py" "--output-dir" "artifacts\pd_risk_model"
        if ($LASTEXITCODE -ne 0) {
            throw "PD risk model training failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "PD risk model artifact is ready."
}

Write-Host "Demo environment is ready. Start the service with: $PythonPath app.py"
