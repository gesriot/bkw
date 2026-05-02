param(
    [string]$PythonVersion = "3.14",
    [string]$ProductName = "BKW",
    [string]$BuildEnv = ".build-venv/windows",
    [string]$OutputDir = "dist/windows",
    [ValidateSet("standalone", "onefile")]
    [string]$Mode = "onefile",
    [ValidateSet("yes", "no", "auto")]
    [string]$Lto = "yes"
)

$ErrorActionPreference = "Stop"
$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

$env:UV_CACHE_DIR = if ($env:UV_CACHE_DIR) { $env:UV_CACHE_DIR } else { Join-Path $RootDir ".uv-cache" }
$env:NUITKA_CACHE_DIR = if ($env:NUITKA_CACHE_DIR) { $env:NUITKA_CACHE_DIR } else { Join-Path $RootDir ".nuitka-cache" }
$env:MPLCONFIGDIR = if ($env:MPLCONFIGDIR) { $env:MPLCONFIGDIR } else { Join-Path $RootDir ".mplconfig" }

$BuildEnvPath = Join-Path $RootDir $BuildEnv
$OutputPath = Join-Path $RootDir $OutputDir

Write-Host "==> Creating build environment: $BuildEnvPath"
Invoke-Checked { uv venv --clear --python $PythonVersion $BuildEnvPath } "uv venv"

$Version = & "$BuildEnvPath/Scripts/python.exe" -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
if ($LASTEXITCODE -ne 0) {
    throw "Reading project version failed with exit code $LASTEXITCODE"
}
$IconPath = Join-Path $RootDir "dist/icons/$ProductName.ico"
$ExePath = Join-Path $OutputPath "$ProductName.exe"
$ZipPath = Join-Path $RootDir "dist/$ProductName-$Version-windows-x64.zip"

Write-Host "==> Installing runtime dependencies into build environment"
$env:UV_PROJECT_ENVIRONMENT = $BuildEnvPath
Invoke-Checked { uv sync --locked } "uv sync"

Write-Host "==> Installing build-only dependencies"
Invoke-Checked { uv pip install --python "$BuildEnvPath/Scripts/python.exe" "nuitka>=4,<5" ordered-set zstandard } "uv pip install"
if (Test-Path Env:\UV_PROJECT_ENVIRONMENT) {
    Remove-Item Env:\UV_PROJECT_ENVIRONMENT
}

if (Test-Path "icon.png") {
    Write-Host "==> Generating Windows icon from icon.png"
    Invoke-Checked { & "$BuildEnvPath/Scripts/python.exe" scripts/make_icon.py --input icon.png --ico $IconPath } "Icon generation"
}

Write-Host "==> Removing previous Windows build output"
Remove-Item -Recurse -Force "$OutputPath/main.dist", "$OutputPath/main.build", "$OutputPath/main.onefile-build", "$OutputPath/$ProductName.dist", $ExePath, $ZipPath -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $OutputPath | Out-Null

$NuitkaArgs = @(
    "--mode=$Mode",
    "--windows-console-mode=disable",
    "--enable-plugin=pyside6",
    "--include-package=bkw_py",
    "--include-package=bkw_ui_app",
    "--include-package=pyqtgraph",
    "--include-package=numpy",
    "--include-module=PySide6.QtOpenGL",
    "--include-module=PySide6.QtOpenGLWidgets",
    "--include-package-data=bkw_py",
    "--include-package-data=pyqtgraph",
    "--include-package-data=numpy",
    "--include-data-dir=$RootDir/bkw_ui/tdf_engine=tdf_engine",
    "--assume-yes-for-downloads",
    "--lto=$Lto",
    "--python-flag=-O",
    "--python-flag=no_docstrings",
    "--output-filename=$ProductName.exe",
    "--output-dir=$OutputPath"
)

if (Test-Path $IconPath) {
    $NuitkaArgs += "--windows-icon-from-ico=$IconPath"
}

if (Test-Path "icon.png") {
    $NuitkaArgs += "--include-data-files=icon.png=icon.png"
}

Write-Host "==> Building Windows application with Nuitka"
Invoke-Checked { & "$BuildEnvPath/Scripts/python.exe" -m nuitka @NuitkaArgs bkw_ui/main.py } "Nuitka build"

if ($Mode -eq "standalone") {
    # Nuitka names the output dir after the entry script (main.dist). Rename it
    # to the product name for a predictable standalone directory.
    $RenamedDist = Join-Path $OutputPath "$ProductName.dist"
    if (Test-Path "$OutputPath/main.dist") {
        if (Test-Path $RenamedDist) {
            Remove-Item -Recurse -Force $RenamedDist
        }
        Rename-Item -Path "$OutputPath/main.dist" -NewName "$ProductName.dist"
    }
    Write-Host "==> Creating ZIP artifact"
    Compress-Archive -Path "$RenamedDist" -DestinationPath $ZipPath -Force
} elseif (-not (Test-Path $ExePath)) {
    throw "Expected onefile executable was not created: $ExePath"
}

Write-Host "==> Done"
if ($Mode -eq "standalone") {
    Write-Host "Dist: $OutputPath/$ProductName.dist"
    Write-Host "ZIP:  $ZipPath"
} else {
    Write-Host "EXE:  $ExePath"
}
