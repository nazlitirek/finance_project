"""Finansal tabloları analiz için okunur hâle getirir: kalem kodları, son 12 ay (TTM), tek çeyrek, ortalama.

İş Yatırım iki şablon kullanır:
- "industrial" (XI_29): sanayi / hizmet şirketleri
- "financial" (UFRS): banka, sigorta, finansal kiralama
Kalem kodları 21.11.2026'da THYAO, AKBNK ve ANSGR tablolarından doğrulandı.
"""

from dataclasses import dataclass

from app.analysis.common import num

# Sanayi/hizmet şablonu (XI_29)
IND = {
    "current_assets": "1A", "cash": "1AA", "short_investments": "1AB", "trade_receivables": "1AC",
    "inventories": "1AF", "noncurrent_assets": "1AK", "total_assets": "1BL",
    "short_liabilities": "2A", "short_financial_debt": "2AA", "long_liabilities": "2B", "long_financial_debt": "2BA",
    "equity": "2N", "parent_equity": "2O", "minority_interest": "2ODA",
    "revenue": "3C", "cogs": "3CA", "gross_profit": "3D", "operating_profit": "3DF",
    "finance_expense": "3HC", "pretax_profit": "3I", "tax": "3IA", "net_profit": "3L", "parent_net_profit": "3Z",
    "depreciation": "4B", "operating_cash_flow": "4C", "capex": "4CAI", "investing_cash_flow": "4CAK",
    "free_cash_flow": "4CB", "financing_cash_flow": "4CBE",
}
# Finans şablonu (UFRS) — ortak kalemler. Aynı kod banka ve sigortada farklı kalem olabilir,
# bu yüzden ek kalemler profile göre ayrılır.
FIN = {"total_assets": "1Z", "equity": "2O", "net_profit": "3Z", "parent_net_profit": "3Z"}
BANK = {**FIN, "loans": "1AF", "deposits": "2A", "net_interest_income": "3C", "net_fees": "3CA",
        "operating_income": "3CE", "loan_provisions": "3CF", "pretax_profit": "3CL"}
INSURANCE = {**FIN, "earned_premiums": "3AA"}
FLOW_PREFIXES = ("3", "4")

Period = tuple[int, int]


def pkey(p: Period) -> str:
    return f"{p[0]}/{p[1]:02d}"


@dataclass
class Financials:
    template: str  # industrial / financial
    values: dict[Period, dict[str, float]]  # dönem → kalem kodu → değer
    inflation: dict[Period, bool | None]
    profile: str = "general"

    @property
    def periods(self) -> list[Period]:
        return sorted(self.values, reverse=True)

    @property
    def latest(self) -> Period | None:
        return self.periods[0] if self.values else None

    def code(self, item: str) -> str | None:
        if self.template == "industrial":
            return IND.get(item)
        return {"bank": BANK, "insurance": INSURANCE}.get(self.profile, FIN).get(item)

    def raw(self, item: str, p: Period) -> float | None:
        c = self.code(item)
        return num(self.values.get(p, {}).get(c)) if c else None

    def is_flow(self, item: str) -> bool:
        c = self.code(item)
        return bool(c) and c.startswith(FLOW_PREFIXES)

    def ttm(self, item: str, p: Period) -> float | None:
        """Son 12 ay: yıllık ise doğrudan; değilse kümülatif(p) + yıllık(y−1) − kümülatif(y−1, p)."""
        y, m = p
        if m == 12:
            return self.raw(item, p)
        a, b, c = self.raw(item, p), self.raw(item, (y - 1, 12)), self.raw(item, (y - 1, m))
        return None if None in (a, b, c) else a + b - c

    def quarter(self, item: str, p: Period) -> float | None:
        """Tek çeyrek değeri (akış kalemleri)."""
        y, m = p
        cur = self.raw(item, p)
        if m == 3 or cur is None:
            return cur
        prev = self.raw(item, (y, m - 3))
        return None if prev is None else cur - prev

    def flow(self, item: str, p: Period) -> float | None:
        return self.ttm(item, p) if self.is_flow(item) else self.raw(item, p)

    def avg(self, item: str, p: Period) -> float | None:
        """Bilanço kalemi için dönem sonu ile bir yıl önceki dönem sonunun ortalaması (yoksa dönem sonu)."""
        cur, prev = self.raw(item, p), self.raw(item, (p[0] - 1, p[1]))
        if cur is None:
            return None
        return (cur + prev) / 2 if prev is not None else cur

    def year_ago(self, p: Period) -> Period:
        return (p[0] - 1, p[1])

    def prev_quarter(self, p: Period) -> Period:
        return (p[0], p[1] - 3) if p[1] > 3 else (p[0] - 1, 12)

    def ebitda_ttm(self, p: Period) -> float | None:
        op, dep = self.ttm("operating_profit", p), self.ttm("depreciation", p)
        return None if op is None or dep is None else op + abs(dep)

    def quarters_available(self) -> int:
        return len(self.values)


def build(rows: list[tuple[int, int, str, float | None, bool | None]], profile: str = "general") -> Financials | None:
    """rows: (yıl, ay, kalem kodu, değer, enflasyon düzeltmeli mi)"""
    values: dict[Period, dict[str, float]] = {}
    inflation: dict[Period, bool | None] = {}
    for y, m, code, v, infl in rows:
        if v is None:
            continue
        values.setdefault((y, m), {})[code] = float(v)
        inflation[(y, m)] = infl
    if not values:
        return None
    sample = next(iter(values.values()))
    if any("1BL" in v for v in values.values()):
        template = "industrial"
    elif any("1Z" in v for v in values.values()):
        template = "financial"
    else:
        template = "industrial" if "1A" in sample else "financial"
    return Financials(template, values, inflation, profile)
