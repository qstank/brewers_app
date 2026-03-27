# Setup script for Brewers POC App with Ollama
# This script checks for and installs Ollama, then pulls the Mistral model

Write-Host "=== Brewers POC App Setup ===" -ForegroundColor Cyan

# Check if Ollama is installed
Write-Host "`nChecking for Ollama installation..." -ForegroundColor Yellow
$ollamaPath = "$env:ProgramFiles\Ollama\ollama.exe"
$ollamaInstalled = Test-Path $ollamaPath

if ($ollamaInstalled) {
    Write-Host "✓ Ollama is already installed at: $ollamaPath" -ForegroundColor Green
} else {
    Write-Host "✗ Ollama not found. Downloading installer..." -ForegroundColor Yellow
    
    # Download Ollama
    $ollamaUrl = "https://ollama.ai/download/OllamaSetup.exe"
    $installerPath = "$env:TEMP\OllamaSetup.exe"
    
    try {
        Write-Host "Downloading from: $ollamaUrl"
        Invoke-WebRequest -Uri $ollamaUrl -OutFile $installerPath -UseBasicParsing
        Write-Host "✓ Download complete" -ForegroundColor Green
        
        # Run installer
        Write-Host "Running Ollama installer..." -ForegroundColor Yellow
        Start-Process -FilePath $installerPath -Wait
        Write-Host "✓ Ollama installation complete" -ForegroundColor Green
        
        # Clean up
        Remove-Item $installerPath -Force
    } catch {
        Write-Host "✗ Error downloading Ollama: $_" -ForegroundColor Red
        Write-Host "Please download manually from https://ollama.ai/" -ForegroundColor Yellow
        exit 1
    }
}

# Wait for Ollama service to start
Write-Host "`nWaiting for Ollama service to start..." -ForegroundColor Yellow
$maxAttempts = 30
$attempt = 0
$ollamaRunning = $false

while ($attempt -lt $maxAttempts) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -ErrorAction Stop
        $ollamaRunning = $true
        Write-Host "✓ Ollama service is running" -ForegroundColor Green
        break
    } catch {
        $attempt++
        Start-Sleep -Seconds 1
    }
}

if (-not $ollamaRunning) {
    Write-Host "✗ Ollama service failed to start" -ForegroundColor Red
    Write-Host "If Ollama is installed, please start it manually:" -ForegroundColor Yellow
    Write-Host "  - Open Ollama from Start Menu, OR" -ForegroundColor Yellow
    Write-Host "  - Run: ollama serve" -ForegroundColor Yellow
    exit 1
}

# Check for Mistral model
Write-Host "`nChecking for Mistral model..." -ForegroundColor Yellow
try {
    $tagsResponse = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing
    $tags = $tagsResponse.Content | ConvertFrom-Json
    $mistralExists = $tags.models | Where-Object { $_.name -like "*mistral*" }
    
    if ($mistralExists) {
        Write-Host "✓ Mistral model is already installed" -ForegroundColor Green
    } else {
        Write-Host "✓ Pulling Mistral model (~4GB, takes a few minutes)..." -ForegroundColor Yellow
        Start-Process -FilePath "$ollamaPath" -ArgumentList "pull mistral" -Wait
        Write-Host "✓ Mistral model ready" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠ Could not verify model status, but Ollama is running" -ForegroundColor Yellow
    Write-Host "You can manually pull the model with: ollama pull mistral" -ForegroundColor Yellow
}

# Create virtual environment if it doesn't exist
Write-Host "`nSetting up Python virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path ".\venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
    Write-Host "✓ Virtual environment created" -ForegroundColor Green
}

# Activate venv and install requirements
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
& .\venv\Scripts\pip.exe install -r requirements.txt --quiet
Write-Host "✓ Dependencies installed" -ForegroundColor Green

Write-Host "`n=== Setup Complete! ===" -ForegroundColor Cyan
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Activate virtual environment: .\venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host "2. Run the app: streamlit run brewers_poc_app.py" -ForegroundColor Yellow
Write-Host "3. Open http://localhost:8501 in your browser" -ForegroundColor Yellow

Write-Host "`nℹ️  Make sure Ollama stays running in the background!" -ForegroundColor Cyan
