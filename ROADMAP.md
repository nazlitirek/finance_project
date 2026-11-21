# BIST Intelligence — Yol Haritası

Her aşama bitince: yapılanlar, test sonuçları ve eksikler raporlanır. Bir aşama testleri geçmeden sonrakine geçilmez.

Durum işaretleri: ✅ bitti · 🔄 devam ediyor · ⏳ bekliyor · ⛔ karar bekliyor

## Aşama 1 — Proje analizi ve mimari ✅
- [x] Çalışma ortamı incelendi (Python, Node, PostgreSQL, Git)
- [x] Veri kaynakları gerçek isteklerle test edildi
- [x] Kullanım koşulları kontrol edildi (Yahoo, KAP, İş Yatırım, TÜİK, BIST)
- [x] ARCHITECTURE.md, ROADMAP.md
- [x] Kararlar verildi: İş Yatırım (fiyat + tablolar, gün sonu), KAP, EVDS, RSS; Yahoo kapalı (bkz. ARCHITECTURE.md §6)
- ⏳ Kullanıcıdan: EVDS API anahtarı

## Aşama 2 — Backend ve veritabanı ✅
- [x] Python 3.14 sanal ortam (`backend/.venv`), `requirements.txt` — 3.12 kurulumu bu bilgisayarda bozuk
- [x] FastAPI iskeleti, `.env` ayarları, loglama (gizli değerler silinir), CORS sadece yerel adresler
- [x] PostgreSQL: `bist_app` kullanıcısı, `bist_intelligence` + `bist_intelligence_test` (`scripts/setup_db.ps1`)
- [x] SQLAlchemy modelleri: 16 tablo + `news_stocks` (haber ↔ hisse)
- [x] Alembic ilk geçiş (`0001`): indeksler, isim araması için trigram indeksi, 6 veri kaynağı kaydı (Yahoo kapalı)
- [x] Uç noktalar: `/api/health`, `/api/stocks`, `/api/stocks/search`, `/api/stocks/{symbol}`
- [x] **Test:** 28 test geçti (ayarlar, log gizleme, Türkçe arama, kısıtlar, uç noktalar, CORS). Upgrade/downgrade denendi.
- Not: Hisse listesi henüz boş; Aşama 3'te KAP'tan doldurulacak.

## Aşama 3 — Veri toplama ✅
- [x] Ortak HTTP katmanı: kaynak başına hız sınırı, 429/5xx'te yeniden deneme, `SourceError`
- [x] KAP: 741 şirket / 785 hisse kodu, 15 ana + alt sektör, analiz profili (banka, sigorta, holding, GYO...)
- [x] İş Yatırım: 3 yıllık günlük fiyat (düzeltilmiş + düzeltilmemiş), BIST 100 kapanışı, ödenmiş sermaye
- [x] Bölünme/temettü sonrası düzeltilmiş geçmiş değişirse 3 yıl otomatik yeniden çekilir
- [x] Finansal tablolar (son 16 çeyrek), kalem → tablo türü, kümülatif bilgisi, TMS 29 işareti, tek çeyrek hesabı
- [x] KAP bildirimleri (hisseyle eşleştirilmiş), haber RSS (4 akış + takip edilen hisseler için Google Haberler)
- [x] Haber ↔ hisse eşleştirme (kod / ad / arama), kopya haber tespiti
- [x] EVDS makro seriler + TCMB günlük kurları
- [x] Zamanlayıcı (backend çalışırken), `data_update_logs`, komut satırı (`python -m app.cli ...`)
- [x] Uç noktalar: fiyat, son fiyat, piyasa hareketleri, finansal tablolar, KAP, haberler, makro, güncelleme logları, hisse yenileme
- [x] **Test:** 104 test geçti (kayıtlı örneklerle, internetsiz). Canlı veriyle denendi.
- **Bilinen sınırlar:**
  - Açılış fiyatı yok → mum grafik tam çizilemez (Aşama 6'da çizgi/HLC grafik)
  - Hacim TL cinsinden, lot değil
  - XU030 ve XBANK endeks verisi yok (sadece BIST 100)
  - Fiyatlar gün sonu; 15 dk güncelleme yok
  - Bankalar ve sigorta şirketleri için nakit akış tablosu yok
  - Tablonun konsolide/solo olduğu bilinmiyor; finans kuruluşlarında TMS 29 durumu "bilinmiyor"
  - TÜFE serisi (TP.FG.J0) 2026-01'de bitiyor; yeni seri kodu bulunmalı. İşsizlik serisinin tanımı teyit edilmeli
  - EVDS ile TCMB günlük kur dosyası aynı gün için küçük fark gösterebiliyor (ör. 20.11.2026: 50,3786 / 50,4028)
  - Yahoo adapteri yazılmadı (kaynak kapalı)

## Aşama 4 — Finansal analiz motoru ✅
- [x] Teknik: SMA 20/50/100/200, EMA 9/21/50/200, RSI, MACD, Stokastik, Williams %R, ROC, Bollinger, ATR, tarihsel oynaklık, std sapma, OBV, MFI, hacim ortalaması, destek/direnç (dönüş noktalarından). VWAP gün içi veri olmadığı için yok.
- [x] Teknik değerlendirme: trend yönü, momentum gücü, aşırı alım/satım, hacim desteği, oynaklık durumu; puan = trend %35 + momentum %30 + hacim %20 + oynaklık %15
- [x] Temel: son 12 ay (TTM), yıllık, çeyreklik yıllık ve çeyrekten çeyreğe büyüme; kârlılık, büyüme, nakit üretimi puanı
- [x] Finansal sağlık: likidite, borçluluk, kârlılık, verimlilik (formül + değer + bir yıl önceki değer); bankalar/sigorta için ayrı oran seti
- [x] Değerleme: F/K, PD/DD, FD/FAVÖK, FD/Satışlar, Fiyat/Nakit akışı; DCF 3 senaryo (iyimser/baz/kötümser), bütün varsayımlar görünür
- [x] Sektör karşılaştırması: aynı dönem, ortalama + medyan, yüzdelik konum, en az 5 şirket kuralı
- [x] Risk: oynaklık, beta (BIST 100), maksimum düşüş, Sharpe, Sortino, aşağı yönlü sapma, ATR, borçluluk, likidite, kâr istikrarsızlığı (100 = düşük risk)
- [x] Genel puan: ağırlıklar `config/scoring.toml`; eksik modüller normalize edilir, kapsama gösterilir
- [x] Uç noktalar: `/api/stocks/{kod}/analysis`, `/analysis/{modül}`, `POST /peers/refresh`
- [x] Hesaplanan oranlar `financial_ratios` tablosuna kaydediliyor
- [x] **Test:** 139 test geçti — RSI, ATR, EMA, DCF gibi hesaplar elle hesaplanmış değerlerle doğrulandı; sıfıra bölme, eksik veri, zarar/negatif değer durumları
- **Bilinen sınırlar:**
  - Sektör puanı için rakiplerin finansal tablolarının çekilmesi gerekir (`POST /api/stocks/{kod}/peers/refresh`)
  - Haber puanı Aşama 5'te (AI)
  - Geçmiş çarpanlar için geçmiş piyasa değeri ≈ düzeltilmiş fiyat × bugünkü pay adedi (yaklaşık)
  - DCF nominal TL ile; risksiz faiz olarak TCMB fonlama maliyeti kullanılıyor; sonuç varsayımlara çok duyarlı
  - Sigorta şirketleri banka eşikleriyle değerlendiriliyor (özkaynak/aktif); ayrı eşik seti eklenebilir
  - `technical_indicators` tablosu kullanılmıyor; göstergeler her istekte fiyatlardan hesaplanıyor (~2,5 sn)

## Aşama 5 — AI entegrasyonu ✅
- [x] AI istemcisi sadece backend'de (`app/ai/client.py`, `app/ai/gemini.py`); sağlayıcı ve model `.env` içinden
- [x] Yapılandırılmış çıktı: Pydantic şemalarıyla doğrulanan JSON (`client.beta.messages.parse`)
- [x] Reddedilen isteklerde sunucu tarafı yedek model; bütün API hataları Türkçe mesaja çevriliyor
- [x] Haber/KAP analizi: kategori, özet, önem, yön, vade, olumlu/olumsuz etkiler, olay tarihi, kopya tespiti
- [x] Haber puanı formülle: önem × ilgi × kaynak güvenilirliği × güncellik; haber sayısı puanı şişirmez
- [x] Prompt injection önlemi: haber metinleri `<untrusted_documents>` içinde, açılı ayraçlar temizleniyor, tespit işaretleniyor
- [x] Genel rapor: 13 bölüm + olumlu/olumsuz faktörler, belirsizlikler, çelişkiler; her bölümde dayanılan veriler ve eksik veriler
- [x] Kesin al/sat ve hedef fiyat ifadeleri denetleniyor; bulunursa bir kez yeniden yazdırılıyor
- [x] Rapor + puanlar + AI'ye giden girdi (snapshot) + veri tarihleri saklanıyor; eski rapor yeniden hesaplanmıyor
- [x] Uç noktalar: `POST /api/stocks/{kod}/report`, `POST /news/analyze`, `GET /stocks/{kod}/reports`, `GET /reports/{id}`
- [x] **Test:** 159 test geçti (sahte AI ile): şema, puan değişmezliği, injection, yeniden deneme, hata durumu, geçmiş rapor değişmezliği
- [x] **Sağlayıcı seçimi (22.11.2026):** Kullanıcı kararıyla varsayılan sağlayıcı **Google Gemini** (`AI_PROVIDER=gemini`, model `GEMINI_MODEL`, varsayılan `gemini-3.8-flash`). Claude desteği korunuyor (`AI_PROVIDER=anthropic`).
- Tahmini maliyet (rapor + haber analizi, ~7 bin giriş, ~10-15 bin çıkış token):
  - Gemini 3.8 Flash: ~0,05–0,10 USD (ücretsiz katman da var; o katmanda Google içeriği ürün geliştirmede kullanabilir)
  - Gemini 4 Carbon (en güçlü akıl yürütme): ~0,15–0,35 USD; 1 Aralık 2026'dan sonra yaklaşık iki katı
  - Claude Opus 5.5: ~0,3–0,5 USD
- [x] Rapordaki "evidence" sayıları otomatik denetleniyor: girdide karşılığı olmayan sayı `unverified_evidence` listesine yazılır
- [x] **Canlı deneme (22.11.2026, THYAO, gemini-3.8-flash):** 18 haber analiz edildi (injection yok), rapor tamamlandı, yasaklı ifade yok,
  78 kanıt sayısının tamamı girdide doğrulandı. Süre ~4 dk; token: ~18 bin giriş / ~15 bin çıkış → yaklaşık 0,07 USD.
- **Test:** 172 test geçti

## Aşama 6 — Frontend ✅
- [x] Next.js 16 + React 19 + TypeScript + Tailwind 4 + shadcn/ui (Base UI) + SWR; koyu/açık tema
- [x] Piyasa özeti: BIST 100 (BIST 30 / Banka için "veri yok"), yükselen/düşen/hacim, son KAP, son haberler, favoriler, kaynak durumu
- [x] Hisse arama (kod veya ad, Türkçe karakterden bağımsız), klavye ile seçim
- [x] Hisse sayfası: fiyat, değişim, hacim, veri tarihi; grafik (1H–3Y; 1G için gün içi veri yok mesajı), SMA/EMA/Bollinger katmanları, TL hacim
- [x] Grafik türü: açılış fiyatı olmadığı için kapanış çizgisi + gün içi en yüksek/en düşük bandı (mum grafik yok)
- [x] Analiz sekmeleri: teknik, temel, finansal sağlık (formül ipucu), değerleme + DCF 3 senaryo, sektör (rakip verisini çek), haber/KAP (AI ile değerlendir), risk, finansal tablolar, rapor geçmişi
- [x] AI rapor sayfası (puanlar, 13 bölüm, dayanılan veriler, eksik veriler, denetim uyarıları)
- [x] Karşılaştırma (2-5 hisse), favoriler, portföy (ağırlıklı ortalama maliyet, gerçekleşen/gerçekleşmemiş K/Z), fiyat alarmları
- [x] Alarm bildirimleri: uygulama içi + tarayıcı bildirimi (sekme ve backend açıkken, dakikada bir kontrol)
- [x] Backend: favoriler, portföy, alarmlar, grafik, karşılaştırma, piyasa özeti uç noktaları; doğrulama hataları Türkçe mesajla
- [x] **Test:** backend 183 test, frontend 7 test (biçimlendirme, API istemcisi); tip denetimi, lint, üretim derlemesi geçti; tarayıcıda gerçek veriyle denendi
- Çalıştırma: backend `cd backend; .\.venv\Scripts\python -m uvicorn app.main:app --port 8000` · frontend `cd frontend; npm run dev` → http://localhost:3000

## Aşama 7 — PDF ve rapor geçmişi ⏳
- ReportLab ile PDF (Türkçe karakter destekli font)
- Rapor geçmişi; eski raporlar kendi tarihli verileriyle açılır
- **Test:** PDF üretimi, geçmiş rapor değişmezliği

## Aşama 8 — Test ve iyileştirme ⏳
- Tüm backend/frontend testleri, finansal doğrulama
- Performans (sorgu süreleri, önbellek)
- Hata senaryoları: kaynak kapalı, API limiti, Claude hatası, PDF hatası, PostgreSQL bağlantı hatası

## Aşama 9 — Yerel çalıştırma ⏳
- README: kurulum, `.env.example`, PostgreSQL kurulumu
- Backend ve frontend başlatma komutları
- Veri güncelleme servisinin çalıştırılması
