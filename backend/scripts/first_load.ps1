# BIST Intelligence - ilk veri yuklemesi (kurulumdan sonra bir kez)
# Sirasiyla: hisse listesi, 3 yillik fiyatlar (tum hisseler, ~20-30 dk), makro veriler, KAP bildirimleri, haberler.
# Her hisse ayri kaydedilir; yarida kesilirse tekrar calistirmak kaldigi yerden devam eder.

$ErrorActionPreference = "Stop"
$backend = Split-Path -Parent $PSScriptRoot
$py = Join-Path $backend ".venv\Scripts\python.exe"
Set-Location $backend

function Invoke-Step([string]$title, [string[]]$cliArgs) {
    Write-Host ""
    Write-Host "== $title ==" -ForegroundColor Cyan
    & $py -m app.cli @cliArgs
    if ($LASTEXITCODE -ne 0) { Write-Host "Uyari: '$title' tamamen basarili olmadi; diger adimlara devam ediliyor." -ForegroundColor Yellow }
}

Invoke-Step "Hisse listesi ve sektorler (KAP)" @("companies")
Invoke-Step "3 yillik gunluk fiyatlar (Is Yatirim, uzun surer)" @("prices", "--all")
Invoke-Step "Makro veriler (EVDS, TCMB)" @("macro")
Invoke-Step "Son 30 gunun KAP bildirimleri" @("disclosures", "--days", "30")
Invoke-Step "Haberler" @("news")

Write-Host ""
Write-Host "Ilk yukleme bitti. Finansal tablolar bir hisse sayfasinda 'Verileri guncelle' ile veya" -ForegroundColor Green
Write-Host "'python -m app.cli financials THYAO' komutuyla cekilir; favori ve portfoydeki hisseler her gece guncellenir." -ForegroundColor Green
