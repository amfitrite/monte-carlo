$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "XAUUSD Time Machine.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)

# Use pythonw.exe so no console popup window appears
$pythonw = "C:\Users\Ruji Tongki\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command pythonw.exe).Source
}

$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"d:\Time Machine\gui.py"'
$shortcut.WorkingDirectory = "d:\Time Machine"
$shortcut.IconLocation = "d:\Time Machine\assets\gold_icon.ico,0"
$shortcut.Description = "XAUUSD Time Machine - Statistical Odds Simulation Engine for Gold"
$shortcut.Save()

Write-Host "Desktop shortcut created successfully at: $shortcutPath"
