# ad-static-creator: install or update everything with one line (Windows PowerShell):
#   irm https://raw.githubusercontent.com/beyondmrk/ad-static-creator/main/bootstrap.ps1 | iex
# Installs Git and Python if missing, clones (or updates) the skill into ~/.claude/skills, then
# runs install.py, which does the rest. Re-run it any time to update.
$ErrorActionPreference = "Stop"

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}
function Test-Python {
    try { python -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>$null; return $LASTEXITCODE -eq 0 }
    catch { return $false }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    winget install -e --id Git.Git --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
}
if (-not (Test-Python)) {
    winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements `
        --override "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1"
    Refresh-Path
    if (-not (Test-Python)) {
        throw "Python 3.11+ is still not on PATH. Turn off the 'python.exe' App execution alias (Settings > Apps > Advanced app settings), open a new PowerShell and re-run."
    }
}

$dir = Join-Path $HOME ".claude\skills\ad-static-creator"
if (Test-Path (Join-Path $dir ".git")) {
    git -C $dir pull --ff-only
} else {
    git clone https://github.com/beyondmrk/ad-static-creator $dir
}
git -C $dir submodule update --init --recursive
python (Join-Path $dir "install.py")
