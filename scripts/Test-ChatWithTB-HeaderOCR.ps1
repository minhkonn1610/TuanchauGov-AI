$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project ".venv\Scripts\python.exe"
$pdfDir = Join-Path $project "data\raw\pdf"

if (!(Test-Path -LiteralPath $python)) {
    throw "Không tìm thấy Python .venv của ChatWithTBv2."
}

$pdfFiles = @(
    Get-ChildItem -LiteralPath $pdfDir -Filter "12904*.pdf" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "*.signed.pdf" }
)
if ($pdfFiles.Count -ne 1) {
    throw "Cần có đúng một PDF mẫu 12904*.signed.pdf trong data\raw\pdf. Không tìm thấy đúng một file; dừng kiểm tra."
}

$ocrPython = Join-Path $project ".venv-ocr\Scripts\python.exe"
if ([string]::IsNullOrWhiteSpace($ocrPython) -or !(Test-Path -LiteralPath $ocrPython)) {
    throw "Không tìm thấy Python có PaddleOCR trong .venv-ocr. Chạy scripts\Setup-ChatWithTB-HeaderOCR-Env.ps1 trước."
}

$oldValue = $env:CHATWITHTB_OCR_PYTHON
try {
    $env:CHATWITHTB_OCR_PYTHON = $ocrPython
    Set-Location -LiteralPath $project
    & $python ".\scripts\test_header_ocr_sample.py" --pdf $pdfFiles[0].FullName
    if ($LASTEXITCODE -ne 0) {
        throw "Kiểm thử OCR chưa đạt. Không nạp lại tài liệu; hãy gửi lại log."
    }
}
finally {
    if ($null -eq $oldValue) {
        Remove-Item Env:\CHATWITHTB_OCR_PYTHON -ErrorAction SilentlyContinue
    } else {
        $env:CHATWITHTB_OCR_PYTHON = $oldValue
    }
}
