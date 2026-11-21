"""SQLAlchemy modelleri.

Ortak kurallar:
- Her dış veri satırı kaynağını (source_id) ve çekilme zamanını (fetched_at) taşır.
- Eksik değerler NULL kalır; tahminle doldurulmaz.
- Tek kullanıcılı yapı: kullanıcı tablosu yok.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Para / fiyat: 6 ondalık. Finansal tablo kalemleri: çok büyük TL değerleri için geniş alan.
Price = Numeric(20, 6)
Amount = Numeric(28, 4)
Volume = Numeric(24, 2)

FRESHNESS = ("realtime", "delayed", "end_of_day", "historical")


def _check_in(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------------------------------------------------------------- kaynaklar ve loglar

class DataSource(TimestampMixin, Base):
    __tablename__ = "data_sources"
    __table_args__ = (_check_in("freshness", FRESHNESS, "ck_data_sources_freshness"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)  # "isyatirim", "kap", "evds" ...
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40))  # prices / financials / disclosures / macro / news
    base_url: Mapped[str | None] = mapped_column(String(300))
    freshness: Mapped[str] = mapped_column(String(20))
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    terms_note: Mapped[str | None] = mapped_column(Text)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class DataUpdateLog(Base):
    __tablename__ = "data_update_logs"
    __table_args__ = (
        _check_in("status", ("running", "success", "partial", "failed"), "ck_data_update_logs_status"),
        Index("ix_data_update_logs_source_started", "source_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    job: Mapped[str] = mapped_column(String(60))  # "prices_daily", "kap_disclosures" ...
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_written: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------- şirketler

class Sector(TimestampMixin, Base):
    __tablename__ = "sectors"
    __table_args__ = (
        # Sektöre uygun analiz yöntemi seçmek için
        _check_in(
            "analysis_profile",
            ("general", "bank", "insurance", "holding", "reit", "leasing_factoring", "other_financial"),
            "ck_sectors_analysis_profile",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))
    analysis_profile: Mapped[str] = mapped_column(String(30), default="general")
    kap_oid: Mapped[str | None] = mapped_column(String(64), unique=True)
    sector_no: Mapped[str | None] = mapped_column(String(40))  # KAP hiyerarşi numarası, ör. "008000.001000."

    stocks: Mapped[list["Stock"]] = relationship(back_populates="sector")
    parent: Mapped["Sector | None"] = relationship(remote_side="Sector.id")


class Stock(TimestampMixin, Base):
    __tablename__ = "stocks"
    __table_args__ = (
        _check_in("instrument_type", ("equity", "index"), "ck_stocks_instrument_type"),
        # Hızlı isim araması için trigram indeksi (pg_trgm uzantısı gerekir)
        Index(
            "ix_stocks_search_name_trgm", "search_name",
            postgresql_using="gin", postgresql_ops={"search_name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True)  # THYAO, XU100
    name: Mapped[str] = mapped_column(String(300))
    search_name: Mapped[str] = mapped_column(String(300))  # normalize_search(symbol + name)
    instrument_type: Mapped[str] = mapped_column(String(10), default="equity")
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))
    isin: Mapped[str | None] = mapped_column(String(12))
    kap_member_oid: Mapped[str | None] = mapped_column(String(64))
    # Ödenmiş sermaye (TL). Pay başı nominal 1 TL olduğundan pay adedine eşittir. Değerleme için.
    paid_in_capital: Mapped[Decimal | None] = mapped_column(Amount)
    paid_in_capital_as_of: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("data_sources.id"))

    sector: Mapped[Sector | None] = relationship(back_populates="stocks")


# ---------------------------------------------------------------- fiyatlar

class StockPrice(Base):
    __tablename__ = "stock_prices"
    __table_args__ = (
        UniqueConstraint("stock_id", "interval", "ts", "source_id", "is_adjusted", name="uq_stock_prices_bar"),
        Index("ix_stock_prices_lookup", "stock_id", "interval", "ts"),
        _check_in("interval", ("15m", "1h", "1d"), "ck_stock_prices_interval"),
        _check_in("freshness", FRESHNESS, "ck_stock_prices_freshness"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    interval: Mapped[str] = mapped_column(String(5))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # mumun başlangıç zamanı
    open: Mapped[Decimal | None] = mapped_column(Price)  # İş Yatırım açılış fiyatı vermiyor → NULL
    high: Mapped[Decimal | None] = mapped_column(Price)
    low: Mapped[Decimal | None] = mapped_column(Price)
    close: Mapped[Decimal | None] = mapped_column(Price)
    avg_price: Mapped[Decimal | None] = mapped_column(Price)  # ağırlıklı ortalama fiyat
    volume: Mapped[Decimal | None] = mapped_column(Volume)  # lot
    turnover: Mapped[Decimal | None] = mapped_column(Amount)  # TL işlem hacmi
    is_adjusted: Mapped[bool] = mapped_column(Boolean, default=False)  # bölünme/temettü düzeltmesi
    freshness: Mapped[str] = mapped_column(String(20))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- finansal tablolar

class FinancialStatement(Base):
    """Uzun format: her satır bir tablo kalemi (ör. 'Dönen Varlıklar') için bir dönemin değeri."""

    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "source_id", "statement_type", "fiscal_year", "fiscal_period",
            "consolidation", "inflation_adjusted", "item_code",
            name="uq_financial_statements_item",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_financial_statements_lookup", "stock_id", "fiscal_year", "fiscal_period"),
        _check_in("statement_type", ("balance", "income", "cashflow"), "ck_fs_statement_type"),
        # "unknown": kaynak konsolide mi solo mu olduğunu belirtmiyor
        _check_in("consolidation", ("consolidated", "solo", "unknown"), "ck_fs_consolidation"),
        CheckConstraint("fiscal_period IN (3, 6, 9, 12)", name="ck_fs_fiscal_period"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    statement_type: Mapped[str] = mapped_column(String(10))
    fiscal_year: Mapped[int] = mapped_column(SmallInteger)
    fiscal_period: Mapped[int] = mapped_column(SmallInteger)  # dönem sonu ayı: 3, 6, 9, 12
    period_end: Mapped[date] = mapped_column(Date)
    is_cumulative: Mapped[bool] = mapped_column(Boolean)  # gelir/nakit akış: yıl başından kümülatif mi
    consolidation: Mapped[str] = mapped_column(String(15))
    # TMS 29: True = enflasyona göre düzeltilmiş, False = değil, NULL = bilinmiyor (teyit edilmedi)
    inflation_adjusted: Mapped[bool | None] = mapped_column(Boolean)
    inflation_basis: Mapped[str | None] = mapped_column(String(200))  # bu değerin hangi kurala dayandığı
    currency: Mapped[str] = mapped_column(String(3), default="TRY")
    item_code: Mapped[str] = mapped_column(String(40))
    item_name_tr: Mapped[str | None] = mapped_column(String(300))
    item_name_en: Mapped[str | None] = mapped_column(String(300))
    value: Mapped[Decimal | None] = mapped_column(Amount)  # TL, birim çarpanı uygulanmış
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinancialRatio(Base):
    __tablename__ = "financial_ratios"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "fiscal_year", "fiscal_period", "consolidation", "inflation_adjusted", "ratio_code",
            name="uq_financial_ratios",
        ),
        Index("ix_financial_ratios_ratio_period", "ratio_code", "fiscal_year", "fiscal_period"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    fiscal_year: Mapped[int] = mapped_column(SmallInteger)
    fiscal_period: Mapped[int] = mapped_column(SmallInteger)
    consolidation: Mapped[str] = mapped_column(String(15))
    inflation_adjusted: Mapped[bool] = mapped_column(Boolean)
    ratio_code: Mapped[str] = mapped_column(String(40))  # "current_ratio", "roe" ...
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))  # NULL = hesaplanamadı
    formula: Mapped[str] = mapped_column(String(300))
    inputs: Mapped[dict] = mapped_column(JSONB, default=dict)  # hesapta kullanılan değerler
    note: Mapped[str | None] = mapped_column(Text)  # ör. "sıfıra bölme", "banka için uygulanamaz"
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TechnicalIndicator(Base):
    __tablename__ = "technical_indicators"
    __table_args__ = (
        UniqueConstraint("stock_id", "interval", "ts", "indicator_code", name="uq_technical_indicators"),
        Index("ix_technical_indicators_lookup", "stock_id", "indicator_code", "interval", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    interval: Mapped[str] = mapped_column(String(5))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    indicator_code: Mapped[str] = mapped_column(String(40))  # "rsi_14", "sma_50" ...
    value: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- makroekonomi

class MacroObservation(Base):
    __tablename__ = "macro_observations"
    __table_args__ = (
        UniqueConstraint("source_id", "series_code", "obs_date", name="uq_macro_observations"),
        Index("ix_macro_observations_series_date", "series_code", "obs_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    series_code: Mapped[str] = mapped_column(String(60))  # "TP.DK.USD.A"
    series_name: Mapped[str] = mapped_column(String(200))
    frequency: Mapped[str] = mapped_column(String(10))  # daily / weekly / monthly
    obs_date: Mapped[date] = mapped_column(Date)  # aylık seride ayın ilk günü
    value: Mapped[Decimal] = mapped_column(Numeric(24, 8))
    unit: Mapped[str | None] = mapped_column(String(40))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- haberler ve KAP

class News(Base):
    __tablename__ = "news"
    __table_args__ = (Index("ix_news_published", "published_at"), Index("ix_news_content_hash", "content_hash"))

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    title: Mapped[str] = mapped_column(String(600))
    summary: Mapped[str | None] = mapped_column(Text)  # RSS özeti; tam metin saklanmaz
    publisher: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # haberin yayın tarihi
    event_date: Mapped[date | None] = mapped_column(Date)  # olayın gerçekleştiği tarih (biliniyorsa)
    content_hash: Mapped[str] = mapped_column(String(64))  # kopya tespiti
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("news.id", ondelete="SET NULL"))
    category: Mapped[str | None] = mapped_column(String(40))
    ai_analysis: Mapped[dict | None] = mapped_column(JSONB)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NewsStock(Base):
    """Haber ↔ hisse eşleşmesi (bir haber birden fazla şirketi ilgilendirebilir)."""

    __tablename__ = "news_stocks"
    __table_args__ = (Index("ix_news_stocks_stock", "stock_id"),)

    news_id: Mapped[int] = mapped_column(ForeignKey("news.id", ondelete="CASCADE"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    match_type: Mapped[str] = mapped_column(String(20))  # "symbol" / "name"


class KapDisclosure(Base):
    __tablename__ = "kap_disclosures"
    __table_args__ = (Index("ix_kap_disclosures_stock_published", "stock_id", "published_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    kap_index: Mapped[int] = mapped_column(BigInteger, unique=True)  # KAP bildirim numarası
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id", ondelete="SET NULL"))
    company_title: Mapped[str] = mapped_column(String(300))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    disclosure_class: Mapped[str | None] = mapped_column(String(20))  # FR (finansal rapor), ODA (özel durum) ...
    disclosure_type: Mapped[str | None] = mapped_column(String(20))
    subject: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(String(500))
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str | None] = mapped_column(String(40))
    ai_analysis: Mapped[dict | None] = mapped_column(JSONB)
    ai_analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------- analiz

class AnalysisReport(Base):
    """AI raporu. Üretildiği andaki girdiler (input_snapshot) ile birlikte değişmeden saklanır."""

    __tablename__ = "analysis_reports"
    __table_args__ = (
        Index("ix_analysis_reports_stock_created", "stock_id", "created_at"),
        _check_in("status", ("pending", "completed", "failed"), "ck_analysis_reports_status"),
        _check_in("overall_label", ("strong", "neutral", "weak"), "ck_analysis_reports_label"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(15), default="pending")
    model: Mapped[str | None] = mapped_column(String(80))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    overall_label: Mapped[str | None] = mapped_column(String(10))
    data_coverage: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))  # 0-1, mevcut modüllerin ağırlık payı
    report: Mapped[dict | None] = mapped_column(JSONB)  # doğrulanmış AI JSON çıktısı
    input_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)  # AI'ye verilen hesaplanmış sonuçlar
    data_as_of: Mapped[dict] = mapped_column(JSONB, default=dict)  # her veri türünün tarihi
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    error: Mapped[str | None] = mapped_column(Text)

    scores: Mapped[list["AnalysisScore"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class AnalysisScore(Base):
    __tablename__ = "analysis_scores"
    __table_args__ = (
        UniqueConstraint("report_id", "module", name="uq_analysis_scores_module"),
        _check_in(
            "module",
            ("technical", "fundamental", "financial_health", "valuation", "sector", "news", "risk"),
            "ck_analysis_scores_module",
        ),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_analysis_scores_range"),
        CheckConstraint("reliability >= 0 AND reliability <= 1", name="ck_analysis_scores_reliability"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("analysis_reports.id", ondelete="CASCADE"))
    module: Mapped[str] = mapped_column(String(20))
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))  # NULL = veri yetersiz, puanlanmadı
    reliability: Mapped[Decimal] = mapped_column(Numeric(5, 4))  # 0-1
    label: Mapped[str | None] = mapped_column(String(10))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)  # kullanılan göstergeler, eşikler
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped[AnalysisReport] = relationship(back_populates="scores")


# ---------------------------------------------------------------- kişisel

class Portfolio(TimestampMixin, Base):
    __tablename__ = "portfolio"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)

    transactions: Mapped[list["PortfolioTransaction"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


class PortfolioTransaction(TimestampMixin, Base):
    __tablename__ = "portfolio_transactions"
    __table_args__ = (
        _check_in("side", ("buy", "sell"), "ck_portfolio_transactions_side"),
        CheckConstraint("quantity > 0", name="ck_portfolio_transactions_quantity"),
        CheckConstraint("price > 0", name="ck_portfolio_transactions_price"),
        CheckConstraint("fee >= 0", name="ck_portfolio_transactions_fee"),
        Index("ix_portfolio_transactions_portfolio_stock", "portfolio_id", "stock_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolio.id", ondelete="CASCADE"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    side: Mapped[str] = mapped_column(String(4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 4))  # lot
    price: Mapped[Decimal] = mapped_column(Price)
    fee: Mapped[Decimal] = mapped_column(Price, default=0)
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(Text)

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), unique=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text)


class PriceAlert(TimestampMixin, Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        _check_in("condition", ("above", "below"), "ck_price_alerts_condition"),
        CheckConstraint("target_price > 0", name="ck_price_alerts_target"),
        Index("ix_price_alerts_active", "is_active", "stock_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"))
    condition: Mapped[str] = mapped_column(String(5))
    target_price: Mapped[Decimal] = mapped_column(Price)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_price: Mapped[Decimal | None] = mapped_column(Price)
    note: Mapped[str | None] = mapped_column(Text)
