"""Arka plan zamanlayıcı (APScheduler). Sadece backend çalışırken çalışır.

Saatler İstanbul saatidir. Kaynak sıklıkları kullanım koşullarına saygı için düşük tutulur.
İş Yatırım günlük veri verdiği için fiyatlar 15 dakikada bir değil, seans sonrası güncellenir.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.ingest import service
from app.sources.base import TR_TZ

log = logging.getLogger(__name__)

# (iş adı, fonksiyon, tetikleyici, açıklama)
SCHEDULE = [
    ("news", service.update_news, IntervalTrigger(minutes=15, timezone=TR_TZ), "Haberler: 15 dakikada bir"),
    ("disclosures", service.update_disclosures, IntervalTrigger(minutes=30, timezone=TR_TZ),
     "KAP bildirimleri: 30 dakikada bir"),
    ("companies", service.update_companies, CronTrigger(hour=7, minute=30, timezone=TR_TZ),
     "Hisse listesi ve sektörler: her gün 07:30"),
    ("macro", service.update_macro, CronTrigger(hour="10,16", minute=45, timezone=TR_TZ),
     "EVDS ve TCMB kurları: her gün 10:45 ve 16:45"),
    ("prices", service.update_prices, CronTrigger(day_of_week="mon-fri", hour=19, minute=0, timezone=TR_TZ),
     "Bütün hisselerin gün sonu fiyatları: hafta içi 19:00"),
    ("financials", service.update_financials, CronTrigger(hour=3, minute=15, timezone=TR_TZ),
     "Favori ve portföy hisselerinin finansal tabloları: her gece 03:15"),
]


def start() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone=TR_TZ, job_defaults={"coalesce": True, "max_instances": 1,
                                                               "misfire_grace_time": 3600})
    for name, fn, trigger, _ in SCHEDULE:
        sched.add_job(fn, trigger, id=name, name=name)
    sched.start()
    log.info("Zamanlayıcı başladı: %s", ", ".join(n for n, *_ in SCHEDULE))
    return sched
