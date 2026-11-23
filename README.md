# BIST Intelligence

Borsa İstanbul hisselerini açık ve ücretsiz kaynaklardan gelen verilerle analiz eden, kişisel kullanım için
yerel bir platform. Teknik analiz, temel analiz, finansal sağlık, değerleme (çarpanlar + DCF), sektör
karşılaştırması, haber/KAP analizi ve risk analizini tek ekranda toplar; yapay zekâ (Gemini veya Claude)
hesaplanan sonuçları yorumlayan bir rapor yazar.

> **Önemli:** Veriler gün sonu ve gecikmelidir, gerçek zamanlı değildir. Puanlar ve AI yorumları yatırım
> tavsiyesi değildir. Ayrıntılı sınırlar için [ROADMAP.md](ROADMAP.md) ve [ARCHITECTURE.md](ARCHITECTURE.md).

## İçindekiler
1. [Gereksinimler](#gereksinimler)
2. [Kurulum](#kurulum)
3. [Çalıştırma](#çalıştırma)
4. [Veri güncellemeleri](#veri-güncellemeleri)
5. [Ayarlar (.env)](#ayarlar-env)
6. [Testler](#testler)
7. [Sorun giderme](#sorun-giderme)
8. [Proje yapısı](#proje-yapısı)

## Gereksinimler

| Araç | Sürüm | Not |
|---|---|---|
| Windows 10/11 | — | Komutlar PowerShell içindir |
| Python | 3.14 (3.12 de çalışır) | python.org veya Microsoft Store |
| Node.js | 22.12 veya üstü | nodejs.org (LTS) |
| PostgreSQL | 15 veya üstü (18 ile denendi) | Kurulumda `postgres` kullanıcısına şifre verin |
| Git | — | |

İsteğe bağlı anahtarlar:
- **TCMB EVDS anahtarı** (ücretsiz): https://evds3.tcmb.gov.tr → üye olun → Profil → API anahtarı. Makro veriler için.
- **Google Gemini anahtarı**: https://aistudio.google.com → Get API key. AI raporları için.
  (Veya Claude: https://console.anthropic.com → API Keys, `AI_PROVIDER=anthropic`.)

## Kurulum

Bütün komutlar proje klasöründen çalıştırılır.

### 1. Projeyi indirin
```powershell
git clone https://github.com/nazlitirek/finance_project.git
cd finance_project
```

### 2. Backend (Python)
```powershell
cd backend
py -3.14 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```
`backend\.env` dosyasını açın:
- `DATABASE_URL` ve `TEST_DATABASE_URL` içindeki `CHANGE_ME` yerine uygulama için **yeni** bir şifre yazın
  (bu, `postgres` yönetici şifresi değildir; uygulamanın kendi kullanıcısı `bist_app` için).
- `EVDS_API_KEY` ve `GEMINI_API_KEY` değerlerini ekleyin (yoksa boş bırakın; ilgili özellikler kapalı kalır).

### 3. Veritabanı
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_db.ps1
.\.venv\Scripts\python -m alembic upgrade head
```
İlk komut `postgres` yönetici şifresini bir kez sorar; uygulama kullanıcısını ve iki veritabanını
(`bist_intelligence`, testler için `bist_intelligence_test`) oluşturur. Şifre hiçbir yere kaydedilmez.

### 4. İlk veri yüklemesi (bir kez, ~20-30 dakika)
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\first_load.ps1
```
Hisse listesi, bütün hisselerin 3 yıllık fiyatları, makro veriler, son 30 günün KAP bildirimleri ve
haberler yüklenir. Yarıda kesilirse tekrar çalıştırın; kaldığı yerden devam eder.

### 5. Frontend (Node.js)
```powershell
cd ..\frontend
npm ci
copy .env.example .env.local
```

## Çalıştırma

Proje klasöründe:
```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```
İki pencere açılır (backend ve frontend) ve tarayıcıda http://localhost:3000 açılır. Kapatmak için iki pencereyi kapatın.

Elle başlatmak isterseniz, iki ayrı terminalde:
```powershell
cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
```powershell
cd frontend; npm run dev
```
API belgeleri: http://127.0.0.1:8000/docs

## Veri güncellemeleri

Backend açıkken otomatik çalışır (İstanbul saati):

| Veri | Sıklık |
|---|---|
| Haberler (RSS + favori/portföy hisseleri için Google Haberler) | 15 dakikada bir |
| KAP bildirimleri | 30 dakikada bir |
| Hisse listesi ve sektörler | Her gün 07:30 |
| EVDS ve TCMB kurları | Her gün 10:45 ve 16:45 |
| Bütün hisselerin gün sonu fiyatları + fiyat alarmları | Hafta içi 19:00 |
| Favori ve portföy hisselerinin finansal tabloları | Her gece 03:15 |

Elle güncelleme (backend klasöründe):
```powershell
.\.venv\Scripts\python -m app.cli prices THYAO ASELS
```
Diğer komutlar: `companies`, `prices --all`, `financials THYAO`, `disclosures --days 7`, `macro`, `news`,
`news-rematch`. Bir hisse sayfasındaki **Verileri güncelle** düğmesi de o hissenin fiyat, tablo ve haberlerini çeker.
Sektör karşılaştırması için hisse sayfasında Sektör sekmesindeki **Rakiplerin verisini çek** düğmesini kullanın.

## Ayarlar (.env)

`backend\.env` (Git'e eklenmez):

| Ayar | Açıklama |
|---|---|
| `DATABASE_URL`, `TEST_DATABASE_URL` | PostgreSQL bağlantıları (uygulama kullanıcısı `bist_app`) |
| `AI_PROVIDER` | `gemini` (varsayılan) veya `anthropic` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Varsayılan model `gemini-3.8-flash` (rapor başına ~0,07 USD) |
| `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` | Claude kullanılacaksa |
| `EVDS_API_KEY` | TCMB EVDS anahtarı |
| `SCHEDULER_ENABLED` | Arka plan güncellemeleri (`true`/`false`) |
| `CORS_ORIGINS` | Sadece yerel frontend adresleri |

Puan ağırlıkları ve eşikleri: [config/scoring.toml](config/scoring.toml). Değiştirdikten sonra backend'i yeniden başlatın.

## Testler

```powershell
cd backend; .\.venv\Scripts\python -m pytest -q
```
```powershell
cd frontend; npm test
```
Backend testleri ayrı test veritabanını (`bist_intelligence_test`) kullanır; ana veriye dokunmaz.
İnternet gerekmez (kaynaklar ve AI sahte yanıtlarla test edilir).

## Sorun giderme

| Sorun | Çözüm |
|---|---|
| Sayfada "Backend'e bağlanılamadı" | Backend penceresi açık mı? http://127.0.0.1:8000/api/health açılıyor mu? |
| "Veritabanına ulaşılamıyor" | Windows Hizmetler'de `postgresql-x64-…` servisinin çalıştığını kontrol edin |
| `setup_db.ps1` şifre hatası | `postgres` yönetici şifresini kontrol edin (PostgreSQL kurulumunda verilen) |
| AI raporu "anahtar gerekli" diyor | `backend\.env` içinde `GEMINI_API_KEY` dolu mu? Backend'i yeniden başlatın |
| Bir hissede fiyat yok veya "eski fiyat" uyarısı | `python -m app.cli prices KOD`; hisse işleme kapalı olabilir |
| Sektör puanı "veri yetersiz" | Sektör sekmesinde "Rakiplerin verisini çek" |
| Makro veride "eski" işareti | TÜFE serisi (TP.FG.J0) 2026-01'de bitiyor; yeni seri kodu bekleniyor |
| `start.ps1` çalışmıyor (betik engeli) | `powershell -ExecutionPolicy Bypass -File .\start.ps1` şeklinde çalıştırın |

## Proje yapısı

```
backend/    FastAPI, SQLAlchemy, Alembic, veri adapterleri, analiz motoru, AI, PDF  (ayrıntı: ARCHITECTURE.md)
frontend/   Next.js 16, React 19, Tailwind, shadcn/ui
config/     scoring.toml — puan ağırlıkları ve eşikleri
start.ps1   uygulamayı başlatır
```

Veri kaynakları: KAP, İş Yatırım (gün sonu fiyat ve finansal tablolar), TCMB EVDS, TCMB günlük kurlar,
haber RSS akışları. Kişisel kullanım içindir; veriler kimseyle paylaşılmaz.
