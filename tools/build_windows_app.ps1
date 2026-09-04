param(
    [string]$OutputRoot = "",
    [string]$PythonPath = "",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) {
    $Stamp = Get-Date -Format "yyyy-MM-dd-HHmm"
    $OutputRoot = Join-Path "C:\Twano\Builds" "$Stamp-Twano-R4-RC1-Windows"
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$Python = if ($PythonPath) {
    [System.IO.Path]::GetFullPath($PythonPath)
} else {
    Join-Path $ProjectRoot ".venv\Scripts\python.exe"
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Run launcher.bat once before building the Windows application."
}
if (Test-Path -LiteralPath $OutputRoot) {
    throw "The output folder already exists. Use a new timestamped folder: $OutputRoot"
}

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Install requirements-build.txt before building: .venv\Scripts\python.exe -m pip install -r requirements-build.txt"
}

$Work = Join-Path $OutputRoot "pyinstaller-work"
$Dist = Join-Path $OutputRoot "dist"
$Spec = Join-Path $OutputRoot "spec"
$SourcePath = Join-Path $ProjectRoot "src"
$EntryPoint = Join-Path $SourcePath "app.py"
$DesignPath = Join-Path $ProjectRoot "design"
$DocsPath = Join-Path $ProjectRoot "docs"
$VersionFile = Join-Path $ProjectRoot "tools\windows_version_info.txt"
$ProductName = "Twano's eBook Manager"
$ExecutableBaseName = "Twano eBook Manager"
$IconPath = Join-Path $DesignPath "branding\twano-book-logo.ico"
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --name $ExecutableBaseName `
        --icon $IconPath `
        --paths $SourcePath `
        --add-data "$DesignPath;design" `
        --add-data "$DocsPath;docs" `
        --version-file $VersionFile `
        --workpath $Work `
        --distpath $Dist `
        --specpath $Spec `
        $EntryPoint
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed."
    }
} finally {
    Pop-Location
}

$OutputName = Split-Path -Leaf $OutputRoot
$PortableZip = Join-Path $OutputRoot "$OutputName-Portable.zip"
Compress-Archive -LiteralPath (Join-Path $Dist $ExecutableBaseName) -DestinationPath $PortableZip
Write-Host "Portable application: $PortableZip"
$PortableHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PortableZip).Hash
Set-Content -LiteralPath "$PortableZip.sha256" -Encoding ascii -Value (
    "$PortableHash  $(Split-Path -Leaf $PortableZip)"
)

if (-not $SkipInstaller) {
    $Iscc = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($null -eq $Iscc) {
        $KnownIsccPaths = @(
            (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe")
        )
        $KnownIscc = $KnownIsccPaths |
            Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
            Select-Object -First 1
        if ($KnownIscc) {
            $Iscc = Get-Item -LiteralPath $KnownIscc
        }
    }
    if ($null -eq $Iscc) {
        Write-Warning "Inno Setup 7 or 6 was not found. Portable application completed; installer was skipped."
    } else {
        $IsccPath = if ($Iscc.Source) { $Iscc.Source } else { $Iscc.FullName }
        & $IsccPath "/DSourceRoot=$(Join-Path $Dist $ExecutableBaseName)" "/DOutputRoot=$OutputRoot" (Join-Path $ProjectRoot "packaging\Twano.iss")
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup failed."
        }
        $Installer = Join-Path $OutputRoot "Twano's eBook Manager Setup.exe"
        if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
            throw "Inno Setup finished without producing the expected installer."
        }
        $InstallerHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash
        Set-Content -LiteralPath "$Installer.sha256" -Encoding ascii -Value (
            "$InstallerHash  $(Split-Path -Leaf $Installer)"
        )
    }
}
