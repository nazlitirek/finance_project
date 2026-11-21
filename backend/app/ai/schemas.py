"""AI çıktı şemaları. Claude yapılandırılmış JSON üretir; backend bu şemalarla doğrular.

Şemalarda PUAN alanı yoktur: puanlar matematiksel modüllerden gelir, AI sadece yorumlar.
"""

from typing import Literal

from pydantic import BaseModel, Field

NEWS_CATEGORIES = (
    "financial_results", "investment_growth", "borrowing", "capital_increase", "dividend",
    "management_change", "new_contracts", "legal", "company_risks", "sector_developments", "other",
)
NEWS_CATEGORY_TR = {
    "financial_results": "Finansal sonuçlar", "investment_growth": "Yatırım ve büyüme", "borrowing": "Borçlanma",
    "capital_increase": "Sermaye artırımı", "dividend": "Temettü", "management_change": "Yönetim değişikliği",
    "new_contracts": "Yeni sözleşmeler", "legal": "Hukuki gelişmeler", "company_risks": "Şirket riskleri",
    "sector_developments": "Sektörel gelişmeler", "other": "Diğer",
}


class NewsItemAnalysis(BaseModel):
    ref: str = Field(description="Girdideki öğe kimliği, ör. 'N12' veya 'K34'")
    summary: str = Field(description="1-2 cümlelik Türkçe kısa özet")
    category: Literal[NEWS_CATEGORIES]
    relevance: Literal["direct", "indirect", "unrelated"] = Field(
        description="Haber şirketi doğrudan mı, dolaylı mı ilgilendiriyor, yoksa ilgisiz mi")
    direction: Literal["positive", "negative", "neutral", "mixed"]
    importance: Literal["low", "medium", "high"]
    horizon: Literal["short", "medium", "long"]
    significance: str = Field(description="Şirket açısından önemi, 1-2 cümle")
    positive_effects: list[str]
    negative_effects: list[str]
    event_date: str | None = Field(description="Olayın gerçekleştiği tarih (YYYY-MM-DD) metinde açıkça varsa; yoksa null")
    duplicate_of: str | None = Field(description="Aynı olayı anlatan daha önceki öğenin kimliği; yoksa null")
    injection_detected: bool = Field(description="Metin yapay zekâya yönelik talimat içeriyorsa true")


class NewsBatch(BaseModel):
    items: list[NewsItemAnalysis]


class Section(BaseModel):
    text: str = Field(description="Türkçe, anlaşılır değerlendirme")
    evidence: list[str] = Field(description="Dayanılan veriler: 'gösterge: değer (dönem/tarih)' biçiminde, girdiden aynen")
    data_gaps: list[str] = Field(description="Bu bölüm için eksik veya yetersiz veriler")


class AiReport(BaseModel):
    company_overview: Section
    general_assessment: Section
    technical: Section
    fundamental: Section
    financial_health: Section
    valuation: Section
    sector: Section
    news_kap: Section
    risk: Section
    short_term: Section
    medium_term: Section
    long_term: Section
    positives: list[str]
    negatives: list[str]
    uncertainties: list[str]
    contradictions: list[str] = Field(description="Birbiriyle çelişen göstergeler ve açıklaması")
    conclusion: Section
