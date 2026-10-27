param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$chatPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ocrRoot = Join-Path $ProjectRoot ".venv-ocr"
$ocrPython = Join-Path $ocrRoot "Scripts\python.exe"
$requirements = Join-Path $PSScriptRoot "requirements-ocr.txt"

if (!(Test-Path -LiteralPath $chatPython)) {
    throw "Không tìm thấy Python trong .venv của ChatWithTBv2: $chatPython"
}
if (!(Test-Path -LiteralPath $requirements)) {
    throw "Không tìm thấy requirements-ocr.txt: $requirements"
}

if (Test-Path -LiteralPath $ocrRoot) {
    if (Test-Path -LiteralPath $ocrPython) {
        Write-Output "OCR virtual environment already exists: $ocrRoot"
        Write-Output "Checking installed packages without changing them..."
        $existingVersions = & $ocrPython -c "from importlib.metadata import version; print(version('paddleocr')); print(version('paddlepaddle'))"
        if ($LASTEXITCODE -ne 0) {
            throw "The existing .venv-ocr is incomplete. It was not deleted or modified; inspect it before retrying."
        }
        $existingVersions = @($existingVersions | ForEach-Object { $_.Trim() })
        if ($existingVersions.Count -lt 2 -or $existingVersions[0] -ne "3.7.0" -or $existingVersions[1] -ne "3.2.2") {
            throw "The existing .venv-ocr package versions do not match the tested pins (paddleocr 3.7.0, paddlepaddle 3.2.2). No files or packages were changed."
        }
        Write-Output "OCR environment check complete. Versions match; no packages were installed."
        return
    }
    throw "The .venv-ocr folder exists but its Python is missing. Nothing was deleted; inspect the folder before retrying."
}

$basePython = (& $chatPython -c "import sys; print(sys._base_executable)").Trim()
if (!(Test-Path -LiteralPath $basePython)) {
    throw "Cannot resolve the base Python interpreter from ChatWithTBv2's .venv."
}
$pythonVersion = (& $basePython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
Write-Output "Creating isolated OCR environment with Python $pythonVersion..."
Write-Output "Target: $ocrRoot"
& $basePython -m venv $ocrRoot
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $ocrPython)) {
    throw "Could not create .venv-ocr. No project source files were changed. Check Python installation and retry after inspection."
}

Write-Output "Upgrading pip inside .venv-ocr..."
& $ocrPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed inside .venv-ocr. ChatWithTBv2's main .venv remains untouched."
}

Write-Output "Installing PaddleOCR only into .venv-ocr. This may download several packages."
& $ocrPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "OCR dependency installation failed. Main ChatWithTBv2 environment was not changed; .venv-ocr was retained for diagnosis."
}

Write-Output "Verifying OCR package versions..."
& $ocrPython -c "from importlib.metadata import version; import paddle; print('paddleocr:', version('paddleocr')); print('paddlepaddle:', version('paddlepaddle')); print('paddle import: PASS')"
if ($LASTEXITCODE -ne 0) {
    throw "OCR environment verification failed. Main ChatWithTBv2 environment was not changed."
}
Write-Output "OCR_ENV_SETUP: PASS"
Write-Output "OCR Python: $ocrPython"
Write-Output "The .venv-ocr environment is separate; ChatWithTBv2's .venv was not modified."
