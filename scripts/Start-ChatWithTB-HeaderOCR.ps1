param(
    [string]$OcrPython = ""
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$chatPython = Join-Path $project ".venv\Scripts\python.exe"

if ([string]::IsNullOrWhiteSpace($OcrPython)) {
    $OcrPython = Join-Path $project ".venv-ocr\Scripts\python.exe"
}

if (!(Test-Path -LiteralPath $OcrPython)) {
    throw "Không tìm thấy Python OCR: $OcrPython. Chạy scripts\Setup-ChatWithTB-HeaderOCR-Env.ps1 trước."
}
if (!(Test-Path -LiteralPath $chatPython)) {
    throw "Không tìm thấy Python .venv của ChatWithTBv2: $chatPython"
}

$env:CHATWITHTB_OCR_PYTHON = $OcrPython
Write-Output "ChatWithTBv2 backend is starting with selective header OCR enabled."
Write-Output "ChatWithTB Python: $chatPython"
Write-Output "OCR Python (.venv-ocr by default): $OcrPython"
Set-Location -LiteralPath $project
& $chatPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000
