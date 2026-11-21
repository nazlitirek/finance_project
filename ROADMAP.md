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

## Aşama 5 — AI entegrasyonu ⏳
- Claude istemcisi (backend), model `.env` içinden
- Prompt tasarımı; haberler "güvenilmeyen veri" bloğunda
- JSON şema + Pydantic doğrulama, hatalı çıktıda yeniden deneme
- Haber analizi + genel rapor (kısa/orta/uzun vade)
- **Test:** şema doğrulama, AI çıktısının hesaplanan puanları değiştirmediği

## Aşama 6 — Frontend ⏳
- Next.js + Tailwind + shadcn/ui, koyu/açık tema
- Dashboard, arama, hisse detay (mum grafik + göstergeler), analiz sekmeleri
- Karşılaştırma, favoriler, portföy, fiyat alarmları (uygulama içi + tarayıcı bildirimi)
- Her veride kaynak + güncelleme zamanı + "gecikmeli" etiketi
- **Test:** bileşen testleri, API istemcisi

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
