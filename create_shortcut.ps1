$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "XAUUSD Time Machine.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)

# Otomatis deteksi folder versi terbaru (misal: Monte Carlo 2.01, Monte Carlo 2.02, dst)
$baseDir = "d:\Time Machine"
$latestVersionDir = Get-ChildItem -Path $baseDir -Directory -Filter "Monte Carlo 2*" |
    Sort-Object Name -Descending |
    Select-Object -First 1

if ($latestVersionDir) {
    $targetDir = $latestVersionDir.FullName
    $versionName = $latestVersionDir.Name
} else {
    $targetDir = $baseDir
    $versionName = "Latest"
}

# Gunakan pythonw.exe agar tidak muncul jendela console hitam (background clean)
$pythonw = "C:\Users\Ruji Tongki\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonw) {
        $pythonw = "pythonw.exe"
    }
}

$shortcut.TargetPath = $pythonw
$shortcut.Arguments = "`"$targetDir\gui.py`""
$shortcut.WorkingDirectory = $targetDir

$iconPath = Join-Path $targetDir "assets\gold_icon.ico"
if (-not (Test-Path $iconPath)) {
    $iconPath = Join-Path $baseDir "assets\gold_icon.ico"
}
$shortcut.IconLocation = "$iconPath,0"
$shortcut.Description = "XAUUSD Time Machine ($versionName) - Statistical Odds Simulation Engine for Gold"
$shortcut.Save()

Write-Host "Desktop shortcut successfully updated to point to: $targetDir ($versionName)"
