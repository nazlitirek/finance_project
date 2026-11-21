"""Veri işlerinin tek giriş noktası (CLI, zamanlayıcı ve API buradan çağırır).

Adapterler süreç boyunca tek örnek: aynı kaynağa giden istekler aynı hız sınırını paylaşır.
"""

from functools import lru_cache

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import PortfolioTransaction, Stock, Watchlist
from app.db.session import get_sessionmaker
from app.ingest import jobs
from app.ingest.runner import JobResult, run_job
from app.sources.evds import EvdsSource
from app.sources.isyatirim import IsYatirimSource
from app.sources.kap import KapSource
from app.sources.rss import RssSource
from app.sources.tcmb_fx import TcmbFxSource


@lru_cache
def kap() -> KapSource:
    return KapSource()


@lru_cache
def isy() -> IsYatirimSource:
    return IsYatirimSource()


@lru_cache
def evds() -> EvdsSource:
    key = get_settings().evds_api_key
    return EvdsSource(key.get_secret_value().strip() if key else None)


@lru_cache
def fx() -> TcmbFxSource:
    return TcmbFxSource()


@lru_cache
def rss() -> RssSource:
    return RssSource()


def _sm():
    return get_sessionmaker()


def active_equities() -> list[str]:
    with _sm()() as s:
        return list(s.scalars(select(Stock.symbol).where(
            Stock.instrument_type == "equity", Stock.is_active.is_(True)).order_by(Stock.symbol)))


def followed_symbols() -> list[str]:
    """Favoriler + portföydeki hisseler (finansal tablo ve haber araması için)."""
    with _sm()() as s:
        fav = s.scalars(select(Stock.symbol).join(Watchlist, Watchlist.stock_id == Stock.id))
        port = s.scalars(select(Stock.symbol).join(PortfolioTransaction, PortfolioTransaction.stock_id == Stock.id))
        return sorted(set(fav) | set(port))


def update_companies() -> JobResult:
    return run_job(_sm(), "kap", "companies", lambda s: jobs.sync_companies(s, kap()))


def update_prices(symbols: list[str] | None = None) -> JobResult:
    symbols = [x.upper() for x in symbols] if symbols else active_equities()
    sid = _single_stock_id(symbols)
    return run_job(_sm(), "isyatirim", "prices_daily", lambda s: jobs.sync_prices(s, isy(), symbols), stock_id=sid)


def update_financials(symbols: list[str] | None = None, quarters: int = 16) -> JobResult:
    symbols = [x.upper() for x in symbols] if symbols else followed_symbols()
    sid = _single_stock_id(symbols)
    return run_job(_sm(), "isyatirim", "financials",
                   lambda s: jobs.sync_financials(s, isy(), symbols, quarters), stock_id=sid)


def update_disclosures(days: int = 3) -> JobResult:
    return run_job(_sm(), "kap", "disclosures", lambda s: jobs.sync_disclosures(s, kap(), days))


def update_macro() -> list[JobResult]:
    return [
        run_job(_sm(), "evds", "macro", lambda s: jobs.sync_evds(s, evds())),
        run_job(_sm(), "tcmb_fx", "fx_today", lambda s: jobs.sync_tcmb_fx(s, fx())),
    ]


def update_news(query_symbols: list[str] | None = None) -> JobResult:
    q = query_symbols if query_symbols is not None else followed_symbols()
    return run_job(_sm(), "rss", "news", lambda s: jobs.sync_news(s, rss(), q))


def rematch_news() -> JobResult:
    return run_job(_sm(), "rss", "news_rematch", jobs.rematch_news)


def refresh_stock(symbol: str) -> list[JobResult]:
    """Hisse sayfası açıldığında: fiyat + finansal tablolar + o hisseye ait haber araması."""
    sym = symbol.upper()
    return [update_prices([sym]), update_financials([sym]), update_news([sym])]


def _single_stock_id(symbols: list[str]) -> int | None:
    if len(symbols) != 1:
        return None
    with _sm()() as s:
        return s.scalar(select(Stock.id).where(Stock.symbol == symbols[0]))
