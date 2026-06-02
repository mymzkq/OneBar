$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$iscc = $null
$pathCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if ($pathCommand) {
    $iscc = $pathCommand.Source
}

$candidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)

if (-not $iscc) {
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $iscc = $candidate
            break
        }
    }
}

if (-not $iscc) {
    Write-Host "Inno Setup compiler ISCC.exe was not found."
    Write-Host "Install Inno Setup 6, then run .\\package.ps1 again."
    exit 1
}

$innoRoot = Split-Path -Parent $iscc
$defaultLanguageFile = Join-Path $innoRoot "Default.isl"
if (-not (Test-Path $defaultLanguageFile)) {
    Write-Host "Inno Setup default language file is missing:"
    Write-Host "  $defaultLanguageFile"
    Write-Host "Reinstall Inno Setup 6, then run .\\package.ps1 again."
    exit 1
}

$installerLanguageDir = Join-Path $ProjectRoot "installer\languages"
$projectLanguageFiles = @(
    (Join-Path $installerLanguageDir "ChineseSimplified.isl"),
    (Join-Path $installerLanguageDir "ChineseTraditional.isl")
)
$missingProjectLanguageFiles = @($projectLanguageFiles | Where-Object { -not (Test-Path $_) })
if ($missingProjectLanguageFiles.Count -gt 0) {
    Write-Host "Project installer Chinese language files are missing:"
    foreach ($file in $missingProjectLanguageFiles) {
        Write-Host "  $file"
    }
    Write-Host ""
    Write-Host "Download them from the Inno Setup source repository:"
    Write-Host "  Files/Languages/Unofficial/ChineseSimplified.isl"
    Write-Host "  Files/Languages/Unofficial/ChineseTraditional.isl"
    Write-Host ""
    Write-Host "Place both files under installer/languages/, then run .\\package.ps1 again."
    exit 1
}

& (Join-Path $ProjectRoot "build.ps1")

$exe = Join-Path $ProjectRoot "dist/OneBar/OneBar.exe"
if (-not (Test-Path $exe)) {
    throw "Cannot package: dist/OneBar/OneBar.exe was not found."
}

Write-Host "Building installer with $iscc..."
& $iscc (Join-Path $ProjectRoot "installer/OneBar.iss")
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup compiler failed with exit code $LASTEXITCODE."
}

Write-Host "Installer build complete. Check the dist directory."
