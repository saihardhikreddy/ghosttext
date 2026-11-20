# GhostText one-time setup: Python venv + llama.cpp (Vulkan) + a small local model.
# Run from this folder:  powershell -ExecutionPolicy Bypass -File setup.ps1
param(
  [string]$LlamaBuild = "b12567",
  [string]$ModelUrl = "https://huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
  Write-Host "Creating Python environment..."
  python -m venv .venv
}
.\.venv\Scripts\python -m pip install -q -r requirements.txt

New-Item -ItemType Directory -Force bin, models | Out-Null
if (-not (Test-Path bin\llama-server.exe)) {
  $zip = "llama-$LlamaBuild-bin-win-vulkan-x64.zip"
  Write-Host "Downloading llama.cpp $LlamaBuild (Vulkan, ~40 MB)..."
  curl.exe -L --fail -o "bin\$zip" "https://github.com/ggml-org/llama.cpp/releases/download/$LlamaBuild/$zip"
  Expand-Archive "bin\$zip" -DestinationPath bin -Force
  Remove-Item "bin\$zip"
}
if (-not (Get-ChildItem models\*.gguf -ErrorAction SilentlyContinue)) {
  Write-Host "Downloading model (~1 GB)..."
  curl.exe -L --fail -o models\model.gguf.part $ModelUrl
  Rename-Item models\model.gguf.part ([IO.Path]::GetFileName($ModelUrl))
}
# Double-clickable shortcut (no console window); pin it to Start or copy it to the desktop.
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$PSScriptRoot\GhostText.lnk")
$lnk.TargetPath = "$PSScriptRoot\.venv\Scripts\pythonw.exe"
$lnk.Arguments = '"' + "$PSScriptRoot\GhostText.pyw" + '"'
$lnk.WorkingDirectory = $PSScriptRoot
$lnk.IconLocation = "$PSScriptRoot\ghosttext.ico"
$lnk.Save()
Write-Host "Done. Start GhostText by double-clicking GhostText.lnk (or GhostText.vbs)."
