# install.ps1 — one-shot installer for JARVIS Mark XXXIX on Windows.
#
# Usage (run in PowerShell):
#   iwr -useb https://raw.githubusercontent.com/atxamov99/jarvis-agent/main/install.ps1 | iex
#
# Environment overrides:
#   $env:JARVIS_HOME    — install directory (default: $HOME\jarvis-agent)
#   $env:JARVIS_BRANCH  — branch to clone (default: main)

$ErrorActionPreference = "Stop"

$RepoUrl    = if ($env:JARVIS_REPO_URL) { $env:JARVIS_REPO_URL } else { "https://github.com/atxamov99/jarvis-agent.git" }
$InstallDir = if ($env:JARVIS_HOME)     { $env:JARVIS_HOME }     else { Join-Path $HOME "jarvis-agent" }
$Branch     = if ($env:JARVIS_BRANCH)   { $env:JARVIS_BRANCH }   else { "main" }

# ── helpers ───────────────────────────────────────────────────────────────────
function Write-Step($msg)    { Write-Host "`n▶ $msg" -ForegroundColor Cyan }
function Write-Ok($msg)      { Write-Host "✓ $msg"   -ForegroundColor Green }
function Write-Warn($msg)    { Write-Host "$msg"     -ForegroundColor Yellow }
function Write-Bad($msg)     { Write-Host "✗ $msg"   -ForegroundColor Red }
function Die($msg) { Write-Bad $msg; exit 1 }

# ── header ────────────────────────────────────────────────────────────────────
Write-Host @"

     ╦  ╔═╗╦═╗╦  ╦╦╔═╗
     ║  ╠═╣╠╦╝╚╗╔╝║╚═╗
     ╝  ╩ ╩╩╚═ ╚╝ ╩╚═╝
     Mark-XXXIX — Voice AI Assistant

"@ -ForegroundColor Blue
Write-Host "Install target: $InstallDir"  -ForegroundColor Blue
Write-Host "OS:             Windows"      -ForegroundColor Blue
Write-Host ""

# ── 1. Python ─────────────────────────────────────────────────────────────────
Write-Step "Checking Python (>= 3.10 required)"
$pyBin = $null
foreach ($cmd in "python", "python3", "py") {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $pyBin = $cmd
        break
    }
}
if (-not $pyBin) {
    Die "Python not found. Install Python 3.10+ from https://python.org first."
}
$pyVer = & $pyBin -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
$pyParts = $pyVer.Split(".")
$pyMaj = [int]$pyParts[0]; $pyMin = [int]$pyParts[1]
if ($pyMaj -lt 3 -or ($pyMaj -eq 3 -and $pyMin -lt 10)) {
    Die "Python $pyVer is too old. Need 3.10 or newer."
}
Write-Ok "Python $pyVer ($pyBin)"

# ── 2. git ────────────────────────────────────────────────────────────────────
Write-Step "Checking Git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Die "Git not found. Install from https://git-scm.com/download/win first."
}
Write-Ok "Git found"

# ── 3. clone or update ────────────────────────────────────────────────────────
Write-Step "Fetching JARVIS source"
if (Test-Path (Join-Path $InstallDir ".git")) {
    Write-Warn "$InstallDir exists — updating from $Branch"
    git -C $InstallDir fetch --quiet origin $Branch
    git -C $InstallDir reset --hard "origin/$Branch" | Out-Null
} elseif (Test-Path $InstallDir) {
    Die "$InstallDir exists but is not a git repo. Move or delete it first."
} else {
    git clone --quiet --branch $Branch $RepoUrl $InstallDir
}
Write-Ok "Source at $InstallDir"

# ── 4. virtualenv + deps ──────────────────────────────────────────────────────
Write-Step "Creating Python virtualenv"
$Venv = Join-Path $InstallDir "venv"
$VPy  = Join-Path $Venv "Scripts\python.exe"
$VPip = Join-Path $Venv "Scripts\pip.exe"

if (-not (Test-Path $Venv)) {
    & $pyBin -m venv $Venv
}
& $VPip install --quiet --upgrade pip setuptools wheel
Write-Ok "Virtualenv ready"

Write-Step "Installing Python dependencies (this may take 2-3 minutes)"
$ReqFile = Join-Path $InstallDir "requirements.txt"
if (Test-Path $ReqFile) {
    & $VPip install --quiet -r $ReqFile
    Write-Ok "Dependencies installed"
} else {
    Write-Warn "No requirements.txt found — skipping"
}

# ── 5. API key ────────────────────────────────────────────────────────────────
Write-Step "Configuring Gemini API key"
$ConfigDir  = Join-Path $InstallDir "config"
$ConfigFile = Join-Path $ConfigDir "api_keys.json"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

$existingKey = $false
if (Test-Path $ConfigFile) {
    $content = Get-Content $ConfigFile -Raw
    if ($content -match '"gemini_api_key"\s*:\s*"[^"]+"') { $existingKey = $true }
}

if ($existingKey) {
    Write-Ok "api_keys.json already contains a key — leaving it alone"
} else {
    Write-Host ""
    Write-Warn "A Gemini API key is required."
    Write-Warn "Get one (free) at: https://aistudio.google.com/apikey"
    $GeminiKey = Read-Host "Paste your Gemini API key (or press Enter to skip)"
    @{
        gemini_api_key = $GeminiKey
        live_model     = ""
        os_system      = "windows"
    } | ConvertTo-Json | Set-Content -Path $ConfigFile -Encoding UTF8
    if ($GeminiKey) { Write-Ok "API key saved" } else { Write-Warn "⚠ Key not set yet — edit $ConfigFile later" }
}

# ── 6. PowerShell profile: `jarvis` function ──────────────────────────────────
Write-Step "Adding 'jarvis' command to PowerShell profile"

if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Force -Path $PROFILE | Out-Null
}

$marker      = "# >>> jarvis-agent >>>"
$markerEnd   = "# <<< jarvis-agent <<<"
$existingProfile = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
if ($existingProfile -and $existingProfile.Contains($marker)) {
    # Strip old block
    $pattern = "(?s)$([regex]::Escape($marker)).*?$([regex]::Escape($markerEnd))\r?\n?"
    $existingProfile = [regex]::Replace($existingProfile, $pattern, "")
    Set-Content -Path $PROFILE -Value $existingProfile.TrimEnd()
}

$jarvisFn = @"

$marker
function jarvis {
    & "$VPy" "$InstallDir\main.py" `$args
}
$markerEnd
"@
Add-Content -Path $PROFILE -Value $jarvisFn
Write-Ok "Added \`jarvis\` function to $PROFILE"

# ── 7. Desktop shortcut (optional) ────────────────────────────────────────────
Write-Step "Creating Desktop shortcut"
try {
    $shortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "Jarvis.lnk"
    $shell    = New-Object -ComObject WScript.Shell
    $sc       = $shell.CreateShortcut($shortcut)
    $sc.TargetPath       = $VPy
    $sc.Arguments        = "`"$InstallDir\main.py`""
    $sc.WorkingDirectory = $InstallDir
    $sc.WindowStyle      = 1
    $sc.IconLocation     = "$InstallDir\jarvis.ico,0"
    $sc.Save()
    Write-Ok "Desktop shortcut: $shortcut"
} catch {
    Write-Warn "Could not create Desktop shortcut: $_"
}

# ── 8. done ───────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host " JARVIS Mark-XXXIX installed successfully!"          -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "To start using it:" -ForegroundColor Yellow
Write-Host "  1. Open a new PowerShell window (or run:  . `$PROFILE)"
Write-Host "  2. Type:                                  jarvis"
Write-Host ""
Write-Host "Installation directory: $InstallDir" -ForegroundColor Yellow
Write-Host ""
