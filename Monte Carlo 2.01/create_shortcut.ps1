$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "Monte Carlo.lnk"
$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)

# Otomatis deteksi folder versi terbaru di D:\Monte Carlo
$baseDir = "D:\Monte Carlo"
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
$shortcut.Description = "Monte Carlo ($versionName) - Statistical Odds Simulation Engine"
$shortcut.Save()

Write-Host "Desktop shortcut created successfully at: $shortcutPath -> $targetDir ($versionName)"
