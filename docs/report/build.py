"""Сборка отчёта об архитектуре Mirea CRM."""

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

import diagrams

LIB = "/usr/share/fonts/liberation"
pdfmetrics.registerFont(TTFont("Body", f"{LIB}/LiberationSerif-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Body-Bold", f"{LIB}/LiberationSerif-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Body-Italic", f"{LIB}/LiberationSerif-Italic.ttf"))
pdfmetrics.registerFont(TTFont("Mono", f"{LIB}/LiberationMono-Regular.ttf"))
pdfmetrics.registerFont(TTFont("Mono-Bold", f"{LIB}/LiberationMono-Bold.ttf"))
pdfmetrics.registerFontFamily(
    "Body", normal="Body", bold="Body-Bold", italic="Body-Italic"
)

INK = colors.HexColor("#1A1A1A")
GREY = colors.HexColor("#555555")
RULE = colors.HexColor("#B8B8B8")

BODY = ParagraphStyle(
    "body", fontName="Body", fontSize=11, leading=15.4, alignment=TA_JUSTIFY,
    firstLineIndent=10 * mm, spaceAfter=2, textColor=INK,
)
PLAIN = ParagraphStyle("plain", parent=BODY, firstLineIndent=0)
LEAD = ParagraphStyle("lead", parent=PLAIN, spaceAfter=6)

H1 = ParagraphStyle(
    "h1", fontName="Body-Bold", fontSize=15, leading=19, spaceBefore=0,
    spaceAfter=10, textColor=INK, alignment=TA_LEFT,
)
H2 = ParagraphStyle(
    "h2", fontName="Body-Bold", fontSize=12.5, leading=16, spaceBefore=13,
    spaceAfter=6, textColor=INK,
)
H3 = ParagraphStyle(
    "h3", fontName="Body-Italic", fontSize=11, leading=14.5, spaceBefore=10,
    spaceAfter=4, textColor=INK,
)
CAPTION = ParagraphStyle(
    "caption", fontName="Body", fontSize=9, leading=12, alignment=TA_CENTER,
    textColor=GREY, spaceBefore=4, spaceAfter=12,
)
CELL = ParagraphStyle("cell", fontName="Body", fontSize=9.2, leading=12, textColor=INK)
CELL_MONO = ParagraphStyle("cellmono", parent=CELL, fontName="Mono", fontSize=8.4)
CELL_HEAD = ParagraphStyle(
    "cellhead", parent=CELL, fontName="Body-Bold", fontSize=9, textColor=INK
)
BULLET = ParagraphStyle(
    "bullet", parent=PLAIN, leftIndent=8 * mm, bulletIndent=4 * mm, spaceAfter=3
)
NOTE = ParagraphStyle(
    "note", parent=PLAIN, leftIndent=6 * mm, rightIndent=2 * mm, fontSize=10.4,
    leading=14.4, spaceBefore=6, spaceAfter=8, borderPadding=0,
)

CONTENT_WIDTH = A4[0] - 30 * mm - 15 * mm

_counters = {"section": 0, "sub": 0, "figure": 0, "table": 0}


def mono(text):
    return f'<font face="Mono" size="9.4">{text}</font>'


class Report(BaseDocTemplate):
    def __init__(self, path):
        super().__init__(
            path, pagesize=A4,
            leftMargin=30 * mm, rightMargin=15 * mm,
            topMargin=20 * mm, bottomMargin=20 * mm,
            title="Mirea CRM — архитектура системы",
            author="Практикум по микросервисной архитектуре",
        )
        frame = Frame(
            self.leftMargin, self.bottomMargin,
            self.width, self.height, id="main",
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        )
        self.addPageTemplates([
            PageTemplate(id="title", frames=[frame], onPage=self._blank),
            PageTemplate(id="main", frames=[frame], onPage=self._footer),
        ])

    def _blank(self, canvas, doc):
        pass

    def _footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont("Body", 9.5)
        canvas.setFillColor(GREY)
        canvas.drawCentredString(A4[0] / 2, 12 * mm, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if hasattr(flowable, "toc_level"):
            self.notify("TOCEntry", (flowable.toc_level, flowable.toc_text, self.page))


def heading(text, level=0):
    _counters["figure"] = _counters["figure"]
    if level == 0:
        _counters["section"] += 1
        _counters["sub"] = 0
        number = f"{_counters['section']}"
        style = H1
    else:
        _counters["sub"] += 1
        number = f"{_counters['section']}.{_counters['sub']}"
        style = H2
    para = Paragraph(f"{number}&nbsp;&nbsp;{text}", style)
    para.toc_level = level
    para.toc_text = f"{number}  {text}"
    return para


def figure(cls, height, caption):
    _counters["figure"] += 1
    drawing = cls(CONTENT_WIDTH, height)
    label = Paragraph(f"Рисунок {_counters['figure']} — {caption}", CAPTION)
    return KeepTogether([Spacer(1, 6), drawing, label])


def table_block(rows, widths, caption=None, head=True):
    data = []
    for i, row in enumerate(rows):
        style = CELL_HEAD if (head and i == 0) else None
        cells = []
        for cell in row:
            if isinstance(cell, tuple):
                text, kind = cell
            else:
                text, kind = cell, "text"
            base = CELL_MONO if kind == "mono" else (style or CELL)
            cells.append(Paragraph(text, base))
        data.append(cells)

    table = Table(data, colWidths=widths, repeatRows=1 if head else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.8, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if head:
        commands.append(("LINEBELOW", (0, 0), (-1, 0), 0.5, INK))
    table.setStyle(TableStyle(commands))

    parts = [Spacer(1, 5), table]
    if caption:
        _counters["table"] += 1
        parts += [Paragraph(f"Таблица {_counters['table']} — {caption}", CAPTION)]
    else:
        parts += [Spacer(1, 9)]
    return [KeepTogether(parts)] if len(data) < 12 else parts


def note(text):
    para = Paragraph(text, NOTE)
    table = Table([[para]], colWidths=[CONTENT_WIDTH], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, 0), 1.4, INK),
        ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return KeepTogether([Spacer(1, 4), table, Spacer(1, 6)])


def bullets(items):
    return [Paragraph(text, BULLET, bulletText="—") for text in items]


def numbered(items):
    return [
        Paragraph(text, BULLET, bulletText=f"{i}.") for i, text in enumerate(items, 1)
    ]
