# Builds dist\GhostText-<version>-win64.zip: GhostText.exe + llama.cpp, no model
# (the app downloads the ~1 GB model on first launch).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$version = (.\.venv\Scripts\python -c "import ghosttext; print(ghosttext.__version__)").Trim()
powershell -ExecutionPolicy Bypass -File build.ps1
$stage = "dist\GhostText"
robocopy bin "$stage\bin" /MIR /NFL /NDL /NJH /NJS | Out-Null
Copy-Item README.md "$stage\README.md"
$zip = "dist\GhostText-$version-win64.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path "$stage\*" -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Release zip: $zip ($([int]((Get-Item $zip).Length / 1MB)) MB)"
exit 0  # robocopy returns 1 on success; keep CI green
