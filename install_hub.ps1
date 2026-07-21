<#
.SYNOPSIS
    AD Report Hub — Automated Installer Wizard

.DESCRIPTION
    Creates the .env file, sets up the Python virtual environment,
    installs requirements, and initializes the database and admin user.
#>

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "             AD Report Hub - Easy Installer               " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# Check for Python
try {
    $pythonVer = python --version 2>&1
    Write-Host "[✔] Found Python: $pythonVer" -ForegroundColor Green
}
catch {
    Write-Error "Python is not installed or not in PATH. Please install Python 3.9+ first."
    exit 1
}

# Prompt for Variables
Write-Host "`n--- Configuration ---" -ForegroundColor Cyan
$port = Read-Host "Port to run the web app on (Default: 8090)"
if ([string]::IsNullOrWhiteSpace($port)) { $port = "8090" }

$ingestToken = Read-Host "Ingest Token for AD Script (Default: my_super_secret_token)"
if ([string]::IsNullOrWhiteSpace($ingestToken)) { $ingestToken = "my_super_secret_token" }

# Generate a strong SECRET_KEY
$secretBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($secretBytes)
$secretKey = [System.BitConverter]::ToString($secretBytes) -replace '-'

$envContent = @"
SECRET_KEY=$secretKey
PORT=$port
INGEST_TOKEN=$ingestToken
"@

Set-Content -Path ".\.env" -Value $envContent -Encoding utf8
Write-Host "[✔] Created .env file successfully!" -ForegroundColor Green

Write-Host "`n--- Virtual Environment ---" -ForegroundColor Cyan
Write-Host "[+] Creating python virtual environment (venv)..."
python -m venv venv

Write-Host "[+] Upgrading PIP..."
.\venv\Scripts\python -m pip install --upgrade pip | Out-Null

Write-Host "[+] Installing dependencies from requirements.txt..."
.\venv\Scripts\pip install -r requirements.txt | Out-Null
Write-Host "[✔] Dependencies installed!" -ForegroundColor Green

Write-Host "`n--- Database Setup ---" -ForegroundColor Cyan
Write-Host "[+] Initializing database..."
# The app creates the database on first import if not exist, so running create_admin.py handles it
.\venv\Scripts\python create_admin.py

Write-Host "`n==========================================================" -ForegroundColor Cyan
Write-Host "                Installation Complete!                    " -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To start the AD Report Hub web application, run:" -ForegroundColor Yellow
Write-Host "  .\venv\Scripts\python app.py"
Write-Host ""
Write-Host "Then access it in your browser at:" -ForegroundColor Yellow
Write-Host "  http://localhost:$port"
Write-Host ""
Write-Host "Remember to configure your Authenticator App (MFA) on your first login."
Write-Host "==========================================================" -ForegroundColor Cyan
