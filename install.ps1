# Installs GhostText for the current user: %LOCALAPPDATA%\Programs\GhostText,
# a Start menu entry, and start-with-Windows (set by the app on first launch).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$dest = Join-Path $env:LOCALAPPDATA "Programs\GhostText"
if (-not (Test-Path dist\GhostText\GhostText.exe)) { throw "Run build.ps1 first." }

# Stop any running copy (installed exe or the dev version).
Get-Process GhostText -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' or Name='python.exe'" |
  Where-Object { $_.CommandLine -like "*GhostText.pyw*" -or $_.CommandLine -like "*-m ghosttext*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-Process llama-server -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep 1

New-Item -ItemType Directory -Force $dest | Out-Null
robocopy dist\GhostText $dest /MIR /XD bin models /NFL /NDL /NJH /NJS | Out-Null
robocopy bin (Join-Path $dest bin) /MIR /NFL /NDL /NJH /NJS | Out-Null
New-Item -ItemType Directory -Force (Join-Path $dest models) | Out-Null
foreach ($m in Get-ChildItem models\*.gguf) {
  $target = Join-Path $dest "models\$($m.Name)"
  if (-not (Test-Path $target)) {
    try { New-Item -ItemType HardLink -Path $target -Target $m.FullName | Out-Null }  # no 1 GB copy
    catch { Copy-Item $m.FullName $target }
  }
}

# Start menu shortcut.
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\GhostText.lnk"))
$lnk.TargetPath = Join-Path $dest "GhostText.exe"
$lnk.WorkingDirectory = $dest
$lnk.Description = "GhostText: offline autocomplete and autocorrect"
$lnk.Save()

# Point start-with-Windows at the installed exe (replaces a dev-version entry).
$run = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if (Get-ItemProperty $run -Name GhostText -ErrorAction SilentlyContinue) {
  Set-ItemProperty $run -Name GhostText -Value "`"$(Join-Path $dest 'GhostText.exe')`""
}

Start-Process (Join-Path $dest "GhostText.exe")
Write-Host "Installed to $dest and started. Find it in the Start menu as GhostText."
