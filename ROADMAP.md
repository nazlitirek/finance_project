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

## Aşama 3 — Veri toplama ⏳
- Adapter arayüzü + kaynak sağlık kontrolü
- Hisse listesi (KAP)
- Tarihsel fiyat (3 yıl) + 15 dk güncelleme (seçilen kaynağa göre)
- Endeksler: XU100, XU030, XBANK
- Finansal tablolar (seçilen kaynağa göre) + normalizasyon (birim, dönem, TMS 29, kümülatif→çeyreklik)
- KAP bildirimleri, haber RSS (hisse kodu/adıyla eşleştirme, kopya tespiti)
- EVDS makro seriler, TCMB kurları
- Zamanlayıcı (APScheduler), `data_update_logs`
- **Test:** her adapter için kayıtlı örnek yanıtlarla (internet olmadan) testler; bir kaynak çökünce diğerlerinin çalıştığı test

## Aşama 4 — Finansal analiz motoru ⏳
- Teknik: SMA/EMA, RSI, MACD, Stochastic, Williams %R, ROC, Bollinger, ATR, tarihsel volatilite, OBV, MFI, hacim ortalaması, VWAP (intraday varsa), destek/direnç
- Temel: büyüme (yıllık/çeyreklik), kârlılık, nakit üretimi
- Finansal sağlık: likidite, borçluluk, kârlılık, verimlilik oranları (formül + değer + önceki dönem + sektör)
- Değerleme: çarpanlar, DCF (3 senaryo, tüm varsayımlar görünür)
- Sektör karşılaştırması (aynı dönem, ortalama + medyan, yetersiz örnek uyarısı)
- Risk: volatilite, beta, max drawdown, Sharpe, Sortino, downside deviation
- Puanlama: 7 modül, 0-100, güvenilirlik oranı, ağırlıklar `config/` içinde
- **Test:** bilinen örnek verilerle doğrulama; sıfıra bölme, eksik veri, negatif değer

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
