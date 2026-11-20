# Builds dist\GhostText\GhostText.exe (no console window). Run after setup.ps1.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
.\.venv\Scripts\python -m pip install -q pyinstaller
if (-not (Test-Path ghosttext.ico)) {
  .\.venv\Scripts\python -c "from ghosttext.app import make_icon; make_icon(256).save('ghosttext.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(256,256)])"
}
# Pre-generate the COM wrappers so the frozen app doesn't have to.
.\.venv\Scripts\python -c "import comtypes.client as c; c.GetModule('oleacc.dll'); c.GetModule('UIAutomationCore.dll')"
.\.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name GhostText --icon ghosttext.ico `
  --collect-data symspellpy --collect-submodules comtypes.gen --hidden-import pystray._win32 `
  --add-data "ghosttext.ico;." GhostText.pyw
Write-Host "Built dist\GhostText\GhostText.exe. Run install.ps1 to install it."
