$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "Installing runtime dependencies..."
python -m pip install -r requirements.txt

$pyinstaller = python -m pip show pyinstaller 2>$null
if (-not $pyinstaller) {
    Write-Host "Installing PyInstaller..."
    python -m pip install pyinstaller
}

$assetsDir = Join-Path $ProjectRoot "assets"
$assetsData = "$assetsDir;assets"
$iconPath = Join-Path $assetsDir "icon.ico"

$localHiddenImports = @(
    "autostart",
    "clipboard_history",
    "config",
    "favorites",
    "file_hub",
    "i18n",
    "island_window",
    "layout_metrics",
    "logger",
    "media_control",
    "paths",
    "search_service",
    "settings_window",
    "system_stats",
    "tray",
    "search",
    "search.engine",
    "search.models",
    "search.providers_apps",
    "search.providers_common",
    "search.providers_files",
    "search.providers_settings",
    "search.providers_system",
    "search.providers_uwp",
    "search.providers_web"
)

$args = @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "OneBar",
    "--icon", $iconPath,
    "--paths", (Join-Path $ProjectRoot "app"),
    "--add-data", $assetsData,
    "--collect-submodules", "winsdk",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", "build",
    "app/main.py"
)

foreach ($module in $localHiddenImports) {
    $args += @("--hidden-import", $module)
}

Write-Host "Building OneBar.exe..."
python -m PyInstaller @args

$exe = Join-Path $ProjectRoot "dist/OneBar/OneBar.exe"
if (-not (Test-Path $exe)) {
    throw "Build failed: dist/OneBar/OneBar.exe was not created."
}

$distIconCandidates = @(
    (Join-Path $ProjectRoot "dist/OneBar/assets/icon.ico"),
    (Join-Path $ProjectRoot "dist/OneBar/_internal/assets/icon.ico")
)
$distIcon = $distIconCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $distIcon) {
    throw "Build failed: bundled assets/icon.ico was not found in dist/OneBar."
}

Write-Host "Build complete: $exe"
