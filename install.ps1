<#
.SYNOPSIS
    OMEGA Installation Script for Windows (PowerShell)
.DESCRIPTION
    Windows equivalent of scripts/install.sh
    Run from inside the extracted "omega" project folder (the one containing
    pyproject.toml, requirements.txt, .env.example).
#>

$ErrorActionPreference = "Stop"

$OmegaVersion       = "1.0.0"
$PythonMinVersion    = [version]"3.10"

function Write-Banner {
    Write-Host ""
    Write-Host "=============================" -ForegroundColor Cyan
    Write-Host "          O M E G A          " -ForegroundColor Cyan
    Write-Host "=============================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Installing OMEGA v$OmegaVersion..."
    Write-Host ""
}

function Get-PythonCommand {
    # Windows usually has 'py' (the launcher) and/or 'python', but NOT 'python3'.
    # Try them in order of preference and validate the version.
    $candidates = @("py -3", "python", "python3")

    foreach ($cmd in $candidates) {
        $parts = $cmd.Split(" ")
        $exe   = $parts[0]

        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            try {
                $verOutput = & $exe $parts[1..($parts.Length-1)] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
                if ($LASTEXITCODE -eq 0 -and $verOutput) {
                    $ver = [version]$verOutput.Trim()
                    if ($ver -ge $PythonMinVersion) {
                        return $cmd
                    }
                }
            } catch {
                continue
            }
        }
    }
    return $null
}

function Check-Python {
    Write-Host "Checking for Python $PythonMinVersion+ ..." -ForegroundColor Cyan
    $script:PythonCmd = Get-PythonCommand

    if (-not $script:PythonCmd) {
        Write-Host "Error: No suitable Python found (need $PythonMinVersion+)." -ForegroundColor Red
        Write-Host "Install it from https://python.org/downloads or run:" -ForegroundColor Yellow
        Write-Host "  winget install Python.Python.3.12" -ForegroundColor Yellow
        Write-Host "Then close and reopen this terminal so PATH updates, and re-run this script." -ForegroundColor Yellow
        exit 1
    }

    $parts = $script:PythonCmd.Split(" ")
    $verOutput = & $parts[0] $parts[1..($parts.Length-1)] -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    Write-Host "[OK] Found Python $verOutput (using '$($script:PythonCmd)')" -ForegroundColor Green
}

function Setup-Venv {
    Write-Host "Setting up virtual environment..." -ForegroundColor Cyan
    if (-not (Test-Path ".venv")) {
        $parts = $script:PythonCmd.Split(" ")
        & $parts[0] $parts[1..($parts.Length-1)] -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Error: failed to create virtual environment." -ForegroundColor Red
            exit 1
        }
    }

    $activateScript = ".\.venv\Scripts\Activate.ps1"
    if (-not (Test-Path $activateScript)) {
        Write-Host "Error: could not find $activateScript" -ForegroundColor Red
        exit 1
    }

    # If script execution is blocked, relax it for this process only (no admin needed).
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
    . $activateScript

    python -m pip install --upgrade pip -q
    Write-Host "[OK] Virtual environment ready" -ForegroundColor Green
}

function Install-Deps {
    Write-Host "Installing dependencies (this may take a few minutes)..." -ForegroundColor Cyan
    pip install -r requirements.txt -q
    Write-Host "[OK] Python dependencies installed" -ForegroundColor Green

    Write-Host "Installing Playwright browsers..." -ForegroundColor Cyan
    python -m playwright install chromium
    Write-Host "[OK] Browser automation ready" -ForegroundColor Green
}

function Install-Package {
    Write-Host "Installing OMEGA package..." -ForegroundColor Cyan
    pip install -e . -q
    Write-Host "[OK] OMEGA installed" -ForegroundColor Green
}

function Setup-Config {
    Write-Host "Setting up configuration..." -ForegroundColor Cyan
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "[!] Created .env file. Please edit it and add your OPENROUTER_API_KEY" -ForegroundColor Yellow
        Write-Host "    Get a free key at: https://openrouter.ai/keys" -ForegroundColor Yellow
    } else {
        Write-Host "[OK] .env already exists" -ForegroundColor Green
    }

    $omegaHome = Join-Path $env:USERPROFILE ".omega"
    foreach ($sub in @("plugins", "memory", "logs", "sandbox", "workflows")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $omegaHome $sub) | Out-Null
    }
    Write-Host "[OK] OMEGA home directory created at $omegaHome" -ForegroundColor Green
}

function Check-OptionalServices {
    Write-Host ""
    Write-Host "Checking optional services..." -ForegroundColor Cyan

    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Host "[OK] Docker found (enables sandboxed code execution)" -ForegroundColor Green
    } else {
        Write-Host "[!] Docker not found (code will run via subprocess fallback)" -ForegroundColor Yellow
    }

    $redisOk = $false
    if (Get-Command redis-cli -ErrorAction SilentlyContinue) {
        $pingResult = redis-cli ping 2>$null
        if ($pingResult -eq "PONG") { $redisOk = $true }
    }
    if ($redisOk) {
        Write-Host "[OK] Redis found and running (enables task queue)" -ForegroundColor Green
    } else {
        Write-Host "[!] Redis not found/running (some background features limited)" -ForegroundColor Yellow
        Write-Host "    Install with: docker run -d -p 6379:6379 redis:7-alpine" -ForegroundColor Yellow
    }
}

function Main {
    Write-Banner
    Check-Python
    Setup-Venv
    Install-Deps
    Install-Package
    Setup-Config
    Check-OptionalServices

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "  OMEGA installation complete!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:"
    Write-Host "  1. Edit .env and add your OpenRouter API key"
    Write-Host "  2. Activate the virtual environment: .\.venv\Scripts\Activate.ps1"
    Write-Host "  3. Run OMEGA: omega run"
    Write-Host ""
    Write-Host "Or start the API server: omega serve"
    Write-Host ""
}

Main
