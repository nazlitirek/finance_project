# BIST Intelligence - uygulamayi baslat
# Backend (http://127.0.0.1:8000) ve frontend (http://localhost:3000) iki ayri pencerede acilir.
# Pencereleri kapatinca uygulama durur. Arka plan veri guncellemeleri sadece backend acikken calisir.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$py = Join-Path $root "backend\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) { throw "backend\.venv bulunamadi. Once README'deki kurulum adimlarini yapin." }
if (-not (Test-Path (Join-Path $root "backend\.env"))) { throw "backend\.env bulunamadi. backend\.env.example dosyasini kopyalayin." }
if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) { throw "frontend\node_modules yok. 'cd frontend; npm ci' calistirin." }

Write-Host "Veritabani guncelleniyor (alembic upgrade head)..."
Push-Location (Join-Path $root "backend")
try {
    & $py -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw "Veritabani guncellenemedi. PostgreSQL servisinin calistigini kontrol edin." }
} finally { Pop-Location }

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\backend'; `$Host.UI.RawUI.WindowTitle = 'BIST backend'; & '$py' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\frontend'; `$Host.UI.RawUI.WindowTitle = 'BIST frontend'; npm run dev"

Write-Host "Baslatildi. Birkac saniye sonra tarayicida acin: http://localhost:3000"
Start-Sleep -Seconds 6
Start-Process "http://localhost:3000"
