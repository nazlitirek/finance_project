"""AI analiz raporunu PDF'e dönüştürür (ReportLab).

- Yazı tipi: ReportLab ile gelen Bitstream Vera (Türkçe karakterleri destekler; ₺ yok, "TL" yazılır).
  Bilgisayarda kurulu yazı tiplerine bağlı değildir.
- PDF, veritabanında saklanan raporun kendisinden üretilir; hiçbir şey yeniden hesaplanmaz.
"""

import os
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

FONT, FONT_BOLD, FONT_ITALIC = "BISTSans", "BISTSans-Bold", "BISTSans-Italic"

MODULE_TR = {
    "technical": "Teknik analiz", "fundamental": "Temel analiz", "financial_health": "Finansal sağlık",
    "valuation": "Değerleme", "sector": "Sektör karşılaştırması", "news": "Haber ve KAP", "risk": "Risk",
}
LABEL_TR = {"strong": "Güçlü", "neutral": "Nötr", "weak": "Zayıf"}
SECTIONS = [
    ("company_overview", "Şirket hakkında"), ("general_assessment", "Genel değerlendirme"),
    ("technical", "Teknik analiz"), ("fundamental", "Temel analiz"), ("financial_health", "Finansal sağlık"),
    ("valuation", "Şirket değerlemesi"), ("sector", "Sektör karşılaştırması"), ("news_kap", "Haber ve KAP analizi"),
    ("risk", "Risk analizi"), ("short_term", "Kısa vadeli görünüm"), ("medium_term", "Orta vadeli görünüm"),
    ("long_term", "Uzun vadeli görünüm"),
]
LISTS = [("positives", "Olumlu faktörler"), ("negatives", "Olumsuz faktörler"),
         ("uncertainties", "Önemli belirsizlikler"), ("contradictions", "Çelişkili göstergeler")]
DISCLAIMER = ("Bu rapor yatırım tavsiyesi değildir. Puanlar belgelenmiş formüllerle hesaplanmış, yapay zekâ yalnızca "
              "hesaplanan sonuçları yorumlamıştır. Veriler gün sonu ve gecikmelidir; DCF model değerleri kesin hedef "
              "fiyat değildir.")


class PdfError(Exception):
    pass


@lru_cache
def _register_fonts() -> None:
    base = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    pdfmetrics.registerFont(TTFont(FONT, os.path.join(base, "Vera.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(base, "VeraBd.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_ITALIC, os.path.join(base, "VeraIt.ttf")))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT_ITALIC, boldItalic=FONT_BOLD)


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName=FONT, fontSize=9.5, leading=13.5, textColor=colors.HexColor("#18181b"))
    return {
        "base": base,
        "title": ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=18, leading=22),
        "subtitle": ParagraphStyle("subtitle", parent=base, fontSize=10.5, textColor=colors.HexColor("#52525b")),
        "h2": ParagraphStyle("h2", parent=base, fontName=FONT_BOLD, fontSize=12, leading=16, spaceBefore=8,
                             spaceAfter=3),
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=10, textColor=colors.HexColor("#52525b")),
        "gap": ParagraphStyle("gap", parent=base, fontSize=7.5, leading=10, textColor=colors.HexColor("#b45309")),
        "warn": ParagraphStyle("warn", parent=base, fontSize=8.5, textColor=colors.HexColor("#b91c1c")),
        "right": ParagraphStyle("right", parent=base, alignment=TA_RIGHT),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=10, bulletIndent=0),
    }


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "—")).replace("\n", "<br/>"), style)


def _score(v) -> str:
    return "—" if v is None else f"{float(v):.1f}".replace(".", ",")


def _date(v) -> str:
    if not v:
        return "—"
    try:
        d = datetime.fromisoformat(str(v))
        return d.strftime("%d.%m.%Y %H:%M") if "T" in str(v) or " " in str(v) else d.strftime("%d.%m.%Y")
    except ValueError:
        return str(v)


def build(data: dict) -> bytes:
    """data: app.ai.report.to_dict çıktısı (saklanan rapor)."""
    if data.get("status") != "completed" or not data.get("report"):
        raise PdfError("Sadece tamamlanmış raporlar PDF olarak indirilebilir.")
    _register_fonts()
    st = _styles()
    r = data["report"]
    analysis = data.get("analysis") or {}
    as_of = data.get("data_as_of") or {}
    story = []

    title = f"{data.get('symbol') or ''} — AI analiz raporu #{data['id']}"
    story += [_p(title, st["title"]), _p(analysis.get("name") or "", st["subtitle"]), Spacer(0, 4)]
    meta = [
        ["Oluşturulma", _date(data.get("created_at")), "Model", data.get("model") or "—"],
        ["Fiyat tarihi", _date(as_of.get("price_date")), "Finansal dönem", as_of.get("financial_period") or "—"],
        ["Genel puan", f"{_score(data.get('overall_score'))} ({LABEL_TR.get(data.get('overall_label'), 'sınıf yok')})",
         "Veri kapsamı", "—" if data.get("data_coverage") is None else f"%{float(data['data_coverage']) * 100:.0f}"],
    ]
    t = Table([[_p(c, st["small"] if i % 2 == 0 else st["base"]) for i, c in enumerate(row)] for row in meta],
              colWidths=[28 * mm, 57 * mm, 30 * mm, 57 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#e4e4e7")),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    story += [t, Spacer(0, 6)]

    # modül puanları
    scores = data.get("scores") or []
    head = [_p(MODULE_TR.get(s["module"], s["module"]), st["small"]) for s in scores]
    vals = [_p(_score(s.get("score")), st["base"]) for s in scores]
    if scores:
        w = 172 * mm / len(scores)
        ts = Table([head, vals], colWidths=[w] * len(scores))
        ts.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#d4d4d8")),
                                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e4e4e7")),
                                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4f4f5"))]))
        story += [ts, _p("Risk puanında 100 düşük risk, 0 yüksek risk demektir.", st["small"]), Spacer(0, 4)]

    for key, label in (("policy_warnings", "Denetimden geçmeyen ifadeler"),
                       ("unverified_evidence", "Girdide doğrulanamayan veriler")):
        if r.get(key):
            story.append(_p(f"{label}: " + "; ".join(r[key]), st["warn"]))

    def section(key: str, label: str):
        s = r.get(key)
        if not isinstance(s, dict):
            return
        block = [_p(label, st["h2"]), _p(s.get("text"), st["base"])]
        if s.get("evidence"):
            block.append(_p("Dayanılan veriler: " + " · ".join(s["evidence"]), st["small"]))
        if s.get("data_gaps"):
            block.append(_p("Eksik veri: " + " · ".join(s["data_gaps"]), st["gap"]))
        story.append(KeepTogether(block[:2]))
        story.extend(block[2:])

    for key, label in SECTIONS:
        section(key, label)
    for key, label in LISTS:
        items = r.get(key) or []
        story.append(_p(label, st["h2"]))
        if items:
            story.extend(Paragraph(escape(str(x)), st["bullet"], bulletText="•") for x in items)
        else:
            story.append(_p("Yok.", st["small"]))
    section("conclusion", "Genel sonuç")

    story += [Spacer(0, 8), _p("Kaynaklar: " + ", ".join(data.get("sources") or []), st["small"]),
              _p(data.get("note") or "", st["small"]), Spacer(0, 4), _p(DISCLAIMER, st["small"])]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(colors.HexColor("#71717a"))
        canvas.drawString(18 * mm, 10 * mm, f"BIST Intelligence · {data.get('symbol') or ''} · rapor #{data['id']}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Sayfa {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=title, author="BIST Intelligence",
                            subject="AI destekli hisse analiz raporu")
    try:
        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    except Exception as exc:  # noqa: BLE001
        raise PdfError(f"PDF oluşturulamadı: {exc.__class__.__name__}") from exc
    return buf.getvalue()


def filename(data: dict) -> str:
    day = str(data.get("created_at") or "")[:10] or "tarihsiz"
    return f"{data.get('symbol') or 'rapor'}_AI_rapor_{data['id']}_{day}.pdf"
