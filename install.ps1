# NotebookLM / book-reader One-Click Installer (Windows PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File install.ps1

$SkillsDirGemini = Join-Path $env:USERPROFILE ".gemini\config\skills\book-reader"
$SkillsDirClaude = Join-Path $env:USERPROFILE ".claude\skills\book-reader"
$RepoDir = $PSScriptRoot

Write-Host "[1/3] Setting up skill directories..." -ForegroundColor Cyan

# Support Gemini Antigravity Skills directory
if (-not (Test-Path (Split-Path $SkillsDirGemini -Parent))) {
    New-Item -ItemType Directory -Path (Split-Path $SkillsDirGemini -Parent) -Force | Out-Null
}
if (-not (Test-Path $SkillsDirGemini)) {
    New-Item -ItemType Directory -Path $SkillsDirGemini -Force | Out-Null
}
Copy-Item -Path "$RepoDir\*" -Destination $SkillsDirGemini -Recurse -Force
Write-Host " -> Installed to Gemini: $SkillsDirGemini" -ForegroundColor Green

# Support Claude Desktop Skills directory
if (Test-Path (Join-Path $env:USERPROFILE ".claude")) {
    if (-not (Test-Path $SkillsDirClaude)) {
        New-Item -ItemType Directory -Path $SkillsDirClaude -Force | Out-Null
    }
    Copy-Item -Path "$RepoDir\*" -Destination $SkillsDirClaude -Recurse -Force
    Write-Host " -> Installed to Claude: $SkillsDirClaude" -ForegroundColor Green
}

# Install Python dependencies
Write-Host "`n[2/3] Installing Python dependencies..." -ForegroundColor Cyan
python -m pip install -r (Join-Path $RepoDir "requirements.txt")

# Run environment diagnosis
Write-Host "`n[3/3] Running environment check..." -ForegroundColor Cyan
python (Join-Path $RepoDir "scripts\env_config.py")
