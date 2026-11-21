# BIST Intelligence — Mimari

Durum: Aşama 1 çıktısı (21.11.2026). Kod henüz yok.

## 1. Çalışma ortamı (kontrol edildi)

| Araç | Durum |
|---|---|
| Python | 3.14.3 (varsayılan), 3.12 ve 3.11 de kurulu. **Backend için 3.12 önerilir** — bazı kütüphanelerin (pandas-ta, TA-Lib) 3.14 desteği belirsiz. |
| Node.js / npm | 22.12.0 / 10.9.0 — Next.js için yeterli |
| PostgreSQL | 18.3 kurulu, `postgresql-x64-18` servisi çalışıyor. `psql` PATH'te değil (`C:\Program Files\PostgreSQL\18\bin`). |
| Docker | Kurulu ama çalışmıyor. Gerekli değil. |
| Git | Kurulu. Proje kendi deposunda (`main` → GitHub). |

## 2. Genel yapı

```
finance_project/
├── backend/                 Python / FastAPI
│   ├── app/
│   │   ├── api/             HTTP uç noktaları (routes)
│   │   ├── core/            ayarlar (.env), loglama, hata tipleri
│   │   ├── db/              SQLAlchemy modelleri, oturum
│   │   ├── sources/         veri kaynağı adapterleri (her kaynak ayrı dosya)
│   │   ├── ingest/          veri toplama işleri + zamanlayıcı (15 dk)
│   │   ├── normalize/       birim, dönem, TMS 29, kümülatif→çeyreklik
│   │   ├── analysis/        teknik, temel, sağlık, değerleme, sektör, risk, haber
│   │   ├── scoring/         0-100 puanlar, ağırlıklar (yapılandırılabilir)
│   │   ├── ai/              Claude istemcisi, prompt, JSON şema doğrulama
│   │   └── reports/         PDF üretimi
│   ├── alembic/             veritabanı geçişleri
│   └── tests/
├── frontend/                Next.js / TypeScript / Tailwind / shadcn/ui
│   └── src/ (app/, components/, lib/api.ts)
├── config/                  puan ağırlıkları, eşikler (YAML)
├── .env.example
├── ARCHITECTURE.md
└── ROADMAP.md
```

Veri akışı:

```
Kaynaklar ──► sources/ (adapter) ──► normalize/ ──► PostgreSQL
                                                     │
                                  analysis/ + scoring/ (saf Python fonksiyonları)
                                                     │
                                  ai/ (Claude sadece yorumlar) ──► reports/ (PDF)
                                                     │
                                    FastAPI ──► Next.js (localhost)
```

Temel kurallar:
- Frontend sadece kendi backend'imize bağlanır. API anahtarları yalnızca backend `.env` dosyasında.
- Her hesaplama, test edilebilen saf bir Python fonksiyonudur. Claude hiçbir hesap yapmaz.
- Bir modül veya kaynak hata verirse diğerleri çalışmaya devam eder.
- Her veri satırı: `source`, `fetched_at`, `as_of` (verinin ait olduğu zaman), `freshness` (`realtime` / `delayed` / `historical` / `end_of_day`).
- Eksik veri doldurulmaz; `NULL` kalır ve puanın güvenilirliği düşer.

## 3. Veri kaynakları — test sonuçları (21.11.2026)

Testler bu bilgisayardan basit HTTP istekleriyle yapıldı.

| Kaynak | Ne için | Erişim testi | Kullanım koşulları | Karar |
|---|---|---|---|---|
| **Yahoo Finance** (chart API) | Günlük + 15 dk fiyat, endeksler (XU100, XU030, XBANK), temettü | ✅ Çalışıyor. THYAO 3 yıl = 753 gün. 15 dk mumlar var. Temel veri uç noktası (quoteSummary) ❌ 401. | ⚠️ Yahoo koşulları "otomatik yollarla veri toplamayı" yasaklıyor. Resmî bir API değil. | Kaynak kaydı var, **kapalı**; adapter yazılmadı (bkz. §6). |
| **Stooq** | Fiyat | ❌ Tarayıcı doğrulaması (JavaScript) istiyor; CSV indirilemiyor. | — | Kullanılamaz. |
| **KAP** | Bildirimler, şirket listesi | ✅ `POST /tr/api/disclosure/members/byCriteria` bildirim listesini JSON veriyor. Şirket listesi sayfası HTML (ayrıştırma gerekir). Resmî, belgelenmiş bir API değil. | ⚠️ Kullanım koşulları sayfası bulunamadı. KAP bilgisi kamuya açık ama otomatik erişimde düşük sıklık şart. MKK'nın resmî (kayıtlı) bir KAP veri servisi var. | Düşük sıklıkla kullanılabilir; koşullar teyit edilmeli. |
| **İş Yatırım** (belgede yok) | Finansal tablolar (bilanço, gelir, nakit akış), günlük fiyat | ✅ JSON veriyor. THYAO çeyreklik tablolar geldi. | ⚠️ Belgelenmemiş, sitenin iç uç noktası. Koşullar sayfası bulunamadı. | **Seçildi:** fiyat (gün sonu) + finansal tablolar. |
| **TCMB EVDS** | Enflasyon, faiz, kur, makro | ⚠️ Yeni adres `evds3.tcmb.gov.tr`. Anahtarsız istek 403 ("key header gerekli"). Ücretsiz kayıtla anahtar alınıyor. | ✅ Resmî, ücretsiz API. | Kullanılacak. **EVDS anahtarı gerekiyor.** |
| **TCMB kurlar** (`today.xml`) | Günlük döviz kuru | ✅ Çalışıyor. | ✅ Resmî, kamuya açık. | EVDS yedeği. |
| **TÜİK** | Enflasyon, sanayi üretimi, büyüme | ✅ Portal açık. Veri uç noktaları tarayıcı uygulaması üzerinden; ayrıca incelenmeli. | ⚠️ robots.txt yapay zekâ botlarını (ClaudeBot vb.) engelliyor. Biz tarayıcı bot değiliz ama dikkat. Aynı göstergelerin çoğu EVDS'de de var. | Önce EVDS; TÜİK'i sonra değerlendir. |
| **Borsa İstanbul** | Resmî fiyat/endeks | ✅ Site açık, robots.txt her şeye izin veriyor. | ⚠️ Gerçek zamanlı ve gecikmeli veri yayını lisansa tabi. Ücretsiz makine erişimi yok. | Sadece referans bilgi (endeks listesi, şirket bilgisi). |
| **Haber RSS** | Haber | ✅ AA Ekonomi, BloombergHT, Dünya, Ekonomim, Google News (hisse koduyla arama) çalışıyor. | ✅ RSS kişisel okuma için yayınlanır. Haber metninin tamamı saklanmaz; başlık + özet + bağlantı. | Kullanılacak. |

### Önemli sonuçlar
1. **Fiyat verisi** için hem ücretsiz hem de koşulları açıkça uygun bir kaynak bulamadım. En yakın seçenekler Yahoo ve İş Yatırım; ikisi de gri alan.
2. **15 dakikalık güncelleme:** Yahoo 15 dk mum veriyor, ama veri gecikmeli. Arayüzde her zaman "gecikmeli" etiketi gösterilecek. Hiçbir veri gerçek zamanlı gösterilmeyecek.
3. **Temel veri:** Yahoo temel veri vermiyor. Tek pratik ücretsiz kaynak İş Yatırım (veya KAP'taki finansal tablo bildirimlerini ayrıştırmak — çok daha zor).

## 3.1 Aşama 3'te doğrulanan veri ayrıntıları (21.11.2026)

| Veri | Kaynak | Ayrıntı |
|---|---|---|
| Hisse listesi | KAP `/tr/bist-sirketler` (sayfa içi veri) | 741 şirket, 785 kod (bazı şirketlerin birden fazla pay kodu var) |
| Sektörler | KAP `/tr/Sektorler` | 15 ana sektör, alt sektörler, 650 hisse eşleşmesi |
| Günlük fiyat | İş Yatırım `HisseTekil` | Kapanış, en yüksek, en düşük, ağırlıklı ortalama, TL hacim. **Açılış yok.** `HGDG_*` düzeltilmiş, `HG_*` düzeltilmemiş |
| BIST 100 | İş Yatırım (her fiyat satırında) | Sadece kapanış. XU030 / XBANK yok |
| Finansal tablolar | İş Yatırım `MaliTablo` | Şablon `XI_29` (sanayi/hizmet) veya `UFRS` (banka/sigorta). Kalem kodu 1-2 bilanço, 3 gelir, 4 nakit akış. Tam TL, gelir/nakit akış kümülatif |
| KAP bildirimleri | KAP `POST /tr/api/disclosure/members/byCriteria` | Haftada ~1.900 bildirim |
| Makro | EVDS3 (`key` başlığıyla) | USD, EUR, fonlama maliyeti, TÜFE (eski seri), işsizlik |
| Haberler | AA, Bloomberg HT, Dünya, Ekonomim RSS + Google Haberler | Başlık, özet, bağlantı |

Zaman: Türkiye sabit UTC+3. Günlük fiyatlar o günün 00:00'ı (İstanbul) ile saklanır.

## 4. Veri kaynağı adapter yapısı

```python
class SourceAdapter(Protocol):
    name: str                       # "yahoo", "kap", "evds" ...
    freshness: Freshness            # delayed / end_of_day / historical
    def health(self) -> SourceHealth
    # sadece desteklediği yöntemleri uygular:
    def prices(self, symbol, start, end, interval) -> PriceFrame
    def financials(self, symbol, period) -> list[StatementRow]
    def disclosures(self, since) -> list[Disclosure]
    def macro(self, series, start, end) -> SeriesFrame
```

- Her adapter kendi hız sınırına (rate limit) ve yeniden deneme kuralına sahip.
- Her çağrı `data_update_logs` tablosuna yazılır (başarı/hata, süre, satır sayısı).
- Kaynaklar `config/sources.yaml` içinde açılıp kapatılabilir.
- Aynı veri iki kaynaktan geliyorsa ikisi de saklanır. Fark eşik üstündeyse işaretlenir.

## 4.1 Analiz motoru (Aşama 4)

```
app/analysis/
  common.py      ortak yapılar (Metric, ModuleResult), güvenli bölme, ölçekleme, ağırlıklı ortalama
  statements.py  kalem kodu eşlemesi (sanayi / banka / sigorta), TTM, tek çeyrek, ortalama
  technical.py   göstergeler + teknik puan
  fundamental.py büyüme, oranlar, temel puan, finansal sağlık puanı
  valuation.py   çarpanlar, DCF (3 senaryo), değerleme puanı
  sector.py      aynı dönem rakip karşılaştırması
  risk.py        piyasa ve finansal risk, risk puanı (100 = düşük risk)
  scoring.py     genel puan (normalize edilmiş ağırlıklı ortalama)
  service.py     veritabanından veri hazırlama, modülleri çalıştırma
config/scoring.toml  bütün ağırlıklar ve eşikler
```

Kurallar: hesaplama fonksiyonları saftır (veritabanı yok) ve test edilir; payda sıfır/negatif ise sonuç `None`
olur, tahmin yapılmaz; her modül puan + güvenilirlik (0-1) + puanın anlamı + notlar döndürür.

## 5. Önemli tasarım kararları

- **Teknik göstergeler kendi kodumuzla** (pandas/NumPy). TA-Lib Windows'ta derleme gerektiriyor; pandas-ta'nın bakımı ve yeni NumPy desteği belirsiz. Kendi fonksiyonlarımız bilinen örnek verilerle test edilecek.
- **TMS 29:** Finansal tablolarda `inflation_adjusted` alanı tutulur. Düzeltilmiş ve düzeltilmemiş tablolar asla aynı hesapta karışmaz.
- **Kümülatif → çeyreklik:** Gelir tablosu kalemleri kümülatif gelir; Q2 = H1 − Q1 gibi hesaplanır. Bilanço kalemlerine uygulanmaz.
- **Sektöre göre yöntem:** Banka, sigorta ve holdingler için ayrı oran setleri. Uygun olmayan oran "uygulanamaz" olarak gösterilir.
- **Zamanlayıcı:** APScheduler, backend süreci içinde. Ayrı bir kuyruk sistemi yok (tek kullanıcı).
- **AI:** Google Gemini (varsayılan) veya Claude API — `.env` → `AI_PROVIDER`. yapılandırılmış JSON çıktısı. Pydantic şemasıyla doğrulanır. Haber ve KAP metinleri "güvenilmeyen veri" olarak ayrı bir blokta verilir; içindeki talimatlar uygulanmaz.
- **Rapor geçmişi:** Rapor, üretildiği andaki girdi verileriyle (snapshot JSON) birlikte saklanır. Eski rapor yeniden hesaplanmaz.

## 6. Verilen kararlar (21.11.2026)

1. **Resmî ve ücretsiz kaynaklar kullanılacak:** KAP (şirket listesi, bildirimler — saatte birkaç istek), TCMB EVDS (makro), TCMB kurları (yedek), haber RSS.
2. **Fiyat ve finansal tablolar: İş Yatırım.** Kişisel kullanım, düşük sıklık (hisse başına günde birkaç istek), veri kimseyle paylaşılmaz. Kullanım koşulları sayfası henüz bulunamadı — kullanıcı tarafından kontrol edilecek.
3. **Güncelleme sıklığı:** İş Yatırım sadece günlük veri veriyor. 15 dk hedefi şimdilik **gün sonu** güncellemesine iner. Arayüzde "gün sonu" etiketi gösterilir.
4. **Yahoo:** Koşulları otomatik toplamayı yasakladığı için adapter yazılacak ama **varsayılan olarak kapalı** olacak.
5. **Uzun vadeli çözüm:** Aracı kurumun müşterilere verdiği bir veri API'si araştırılacak (15 dk fiyat için). Adapter yapısı sayesinde kaynak sonradan değiştirilebilir.
6. **EVDS API anahtarı:** Kullanıcı evds3.tcmb.gov.tr üzerinden alacak.
7. **Git:** Proje kendi deposunda: github.com/nazlitirek/finance_project.
