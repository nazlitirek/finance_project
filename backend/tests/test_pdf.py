"""PDF rapor testleri: Türkçe karakter, içerik, hata durumları, uç nokta."""

from io import BytesIO

import pytest
from fastapi.encoders import jsonable_encoder
from pypdf import PdfReader

from app.ai import client as ai_client
from app.reports import pdf
from tests.test_ai import FakeAI, world  # noqa: F401  (fixture)


def _report_dict(**over):
    sec = {"text": "Şirketin kârlılığı ılımlı; İŞ BANKASI ve ğüşıöç harfleri.", "evidence": ["roe: 0.1478 (2026/09)"],
           "data_gaps": ["Pazar payı verisi yok"]}
    rep = {k: sec for k in ("company_overview", "general_assessment", "technical", "fundamental", "financial_health",
                            "valuation", "sector", "news_kap", "risk", "short_term", "medium_term", "long_term",
                            "conclusion")}
    rep.update(positives=["Güçlü nakit"], negatives=[], uncertainties=["Kur riski"], contradictions=[],
               policy_warnings=[], unverified_evidence=[])
    d = {"id": 7, "symbol": "THYAO", "created_at": "2026-11-22T10:00:00+03:00", "status": "completed",
         "model": "gemini-3.8-flash", "overall_score": 50.0, "overall_label": "neutral", "data_coverage": 0.9,
         "data_as_of": {"price_date": "2026-11-20", "financial_period": "2026/09"}, "sources": ["KAP"],
         "error": None, "report": rep, "analysis": {"name": "TÜRK HAVA YOLLARI A.O."},
         "scores": [{"module": "risk", "score": 63.4, "reliability": 1, "label": None, "details": {}}],
         "note": "Bu rapor yeniden hesaplanmaz."}
    d.update(over)
    return d


def _text(b: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(b)).pages)


def test_pdf_contains_turkish_text_and_sections():
    b = pdf.build(_report_dict())
    assert b.startswith(b"%PDF")
    t = _text(b)
    for s in ("TÜRK HAVA YOLLARI", "İŞ BANKASI", "ğüşıöç", "Kısa vadeli görünüm", "Önemli belirsizlikler",
              "Eksik veri: Pazar payı verisi yok", "yatırım tavsiyesi değildir", "Sayfa 1"):
        assert s in t, s


def test_pdf_shows_check_warnings():
    d = _report_dict()
    d["report"]["unverified_evidence"] = ["valuation: hedef: 999"]
    assert "Girdide doğrulanamayan veriler" in _text(pdf.build(d))


def test_pdf_rejects_incomplete_report():
    with pytest.raises(pdf.PdfError):
        pdf.build(_report_dict(status="failed", report={"news_step": {}}))


def test_filename():
    assert pdf.filename(_report_dict()) == "THYAO_AI_rapor_7_2026-11-22.pdf"


def test_pdf_endpoint(client, db, world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ai_client, "structured", FakeAI())
    rid = client.post("/api/stocks/THYAO/report").json()["id"]
    r = client.get(f"/api/reports/{rid}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert f"THYAO_AI_rapor_{rid}_" in r.headers["content-disposition"]
    assert "TÜRK HAVA YOLLARI" in _text(r.content)
    assert client.get("/api/reports/999999/pdf").status_code == 404


def test_pdf_endpoint_failed_report_is_409(client, db, world, monkeypatch):  # noqa: F811
    from app.ai.client import AIError
    monkeypatch.setattr(ai_client, "structured", FakeAI(error=AIError("bağlantı yok", "connection")))
    rid = client.post("/api/stocks/THYAO/report").json()["id"]
    r = client.get(f"/api/reports/{rid}/pdf")
    assert r.status_code == 409 and "tamamlanmış" in r.json()["message"]
