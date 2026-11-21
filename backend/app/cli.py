"""Veri güncelleme komutları.

Kullanım (backend klasöründen):
    python -m app.cli companies                 KAP'tan hisse listesi ve sektörler
    python -m app.cli prices THYAO ASELS        belirli hisselerin günlük fiyatları (3 yıl geriye)
    python -m app.cli prices --all              bütün aktif hisseler (~20 dk)
    python -m app.cli financials THYAO          finansal tablolar (son 16 çeyrek)
    python -m app.cli disclosures --days 7      KAP bildirimleri
    python -m app.cli macro                     EVDS + TCMB kurları
    python -m app.cli news [THYAO ...]          haber RSS (+ verilen hisseler için Google Haberler)
    python -m app.cli news-rematch              eşleştirme kuralları değişince haberleri yeniden eşleştir
"""

import argparse
import sys

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.ingest import service
from app.ingest.runner import JobResult


def _print(results: list[JobResult]) -> int:
    worst = 0
    for r in results:
        print(f"[{r.status:>7}] {r.source}/{r.job}: {r.rows} satır" + (f" — {r.message}" if r.message else ""))
        if r.status == "failed":
            worst = 1
    return worst


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    settings = get_settings()
    setup_logging(settings.log_level, settings.secret_values())

    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("companies")
    pr = sub.add_parser("prices")
    pr.add_argument("symbols", nargs="*")
    pr.add_argument("--all", action="store_true")
    fi = sub.add_parser("financials")
    fi.add_argument("symbols", nargs="*")
    fi.add_argument("--quarters", type=int, default=16)
    di = sub.add_parser("disclosures")
    di.add_argument("--days", type=int, default=3)
    sub.add_parser("macro")
    ne = sub.add_parser("news")
    ne.add_argument("symbols", nargs="*")
    sub.add_parser("news-rematch")
    a = p.parse_args(argv)

    if a.cmd == "companies":
        return _print([service.update_companies()])
    if a.cmd == "prices":
        if not a.symbols and not a.all:
            p.error("hisse kodu verin veya --all kullanın")
        return _print([service.update_prices(None if a.all else a.symbols)])
    if a.cmd == "financials":
        return _print([service.update_financials(a.symbols or None, a.quarters)])
    if a.cmd == "disclosures":
        return _print([service.update_disclosures(a.days)])
    if a.cmd == "macro":
        return _print(service.update_macro())
    if a.cmd == "news":
        return _print([service.update_news(a.symbols)])
    if a.cmd == "news-rematch":
        return _print([service.rematch_news()])
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
