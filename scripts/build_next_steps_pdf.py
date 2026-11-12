"""Render the reviewed Pi runbook as a shareable PDF (documentation tool only).

Requires ReportLab; it is not an application/runtime dependency. From repo root:
    python scripts/build_next_steps_pdf.py
Regenerate after editing docs/hardware/PI-RUNBOOK.md; inspect every rendered page.
"""
import html
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Preformatted, Spacer, PageBreak, Table, TableStyle, KeepTogether,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/hardware/PI-RUNBOOK.md"
OUTPUT = ROOT / "output/pdf/CogniSight-next-steps.pdf"
BLUE = colors.HexColor("#2059B5")
INK = colors.HexColor("#25324A")
MUTED = colors.HexColor("#5E6A7C")


def ascii_text(text):
    return text.translate(str.maketrans({
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2011": "-", "\u00a0": " ",
        "\u2192": "->", "\u2194": "<->", "\u00d7": "x", "\u2026": "...",
    }))


def inline(text):
    text = ascii_text(text)
    # Relative documentation links point to the public repository, not local files.
    def link(match):
        label, target = match.groups()
        if "://" not in target:
            p = (SOURCE.parent / target.split('#')[0]).resolve()
            target = "https://github.com/jahnvik31/CogniSight/blob/main/" + str(p.relative_to(ROOT))
        return f'<link href="{html.escape(target, quote=True)}" color="#2059B5">{html.escape(label)}</link>'
    # Protect generated link tags while escaping ordinary Markdown prose.
    links = []
    def protect(match):
        links.append(link(match))
        return f"LINKTOKEN{len(links)-1}END"
    text = re.sub(r"\[([^]]+)\]\(([^)]+)\)", protect, text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier" size="9">\1</font>', text)
    for i, value in enumerate(links):
        text = text.replace(f"LINKTOKEN{i}END", value)
    return text


BODY = ParagraphStyle("Body", fontName="Helvetica", fontSize=10.2, leading=14.4,
                      textColor=INK, spaceAfter=8)
H1 = ParagraphStyle("Step", parent=BODY, fontName="Helvetica-Bold", fontSize=15,
                    leading=19, textColor=BLUE, spaceBefore=16, spaceAfter=9,
                    keepWithNext=False)
H2 = ParagraphStyle("Substep", parent=H1, fontSize=11.5, leading=15, spaceBefore=12)
TITLE = ParagraphStyle("Title", parent=H1, fontSize=31, leading=35, spaceBefore=0)
CODE = ParagraphStyle("Code", fontName="Courier", fontSize=8.1, leading=11,
                      textColor=INK, backColor=colors.HexColor("#F0F4FA"),
                      borderPadding=9, spaceBefore=6, spaceAfter=12)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=9, leading=13, textColor=MUTED)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#DCE3ED"))
    canvas.line(42, 38, A4[0]-42, 38)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(42, 25, "CogniSight | next execution steps | 12 November 2026")
    canvas.drawRightString(A4[0]-42, 25, str(doc.page))
    canvas.restoreState()


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    story = [Paragraph("CogniSight", TITLE),
             Paragraph("What to do next on the Pi", H1),
             Paragraph("A practical guide for Jahnvi and the contributor with the physical devices.", BODY),
             Spacer(1, 10)]
    rows = [
        ("Start here", "Laptop and Pi on the same Wi-Fi. SSH user: jahnvi. Hostname: cognisight.local. The IP and installed OS release still need checking."),
        ("Software prepared", "Recognition/context, verified GPSD location/status, caregiver monitoring, module contracts, native diagnostics and software integration checks. Read docs/VALIDATION.md for exact results."),
        ("Camera first", "Confirm the 22-pin Pi / 15-pin camera cable with power disconnected. Identify the real sensor, take a private test picture and check visible preview."),
        ("Audio later", "The owned headset is AUX. Select a compatible USB sound adapter with microphone input when needed. Do not expect the Pi 5 to have an analogue headset jack."),
        ("GNSS stays off", "The reported SIMA7670C/RS232 board is not proven to support GNSS. Identify its exact manual and electrical interface before connecting it. Do not wire RS232 to GPIO."),
        ("Phone last", "Start one working app, then configure Caddy HTTPS and trust only its verified public root certificate. Never bypass a certificate warning."),
    ]
    table = Table([[Paragraph(a, H2), Paragraph(b, BODY)] for a,b in rows],
                  colWidths=[108, A4[0]-84-108], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),10),
        ("RIGHTPADDING",(0,0),(-1,-1),10), ("TOPPADDING",(0,0),(-1,-1),8),
        ("BOTTOMPADDING",(0,0),(-1,-1),8),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.HexColor("#F2F6FD"), colors.white]),
        ("LINEBELOW",(0,0),(-1,-1),0.4,colors.HexColor("#DCE3ED")),
    ]))
    story += [table, Spacer(1,12),
        Paragraph("How to use this guide", H2),
        Paragraph("Every numbered step says where to type, what to expect and what to do if it fails. Stop at a failed checkpoint. Device instructions are reviewed procedures; they have not been executed on this Pi. Indoor navigation remains deferred.", BODY),
        Paragraph("The following pages reproduce the maintained SSH runbook. Links refer to the repository and official sources. Keep passwords, face samples, recordings, locations and private keys out of shared files.", SMALL),
        PageBreak()]
    lines = SOURCE.read_text().splitlines()
    paragraph, code, in_code = [], [], False

    def flush():
        if paragraph:
            body = Paragraph(inline(" ".join(paragraph)), BODY)
            if story and isinstance(story[-1], Paragraph) and story[-1].style.name in ("Step", "Substep"):
                heading = story.pop()
                story.append(KeepTogether([heading, body]))
            else:
                story.append(KeepTogether([body]))
            paragraph.clear()

    for line in lines:
        if line.startswith("```"):
            flush()
            if in_code:
                content = ascii_text("\n".join(code))
                if any(len(x) > 110 for x in content.splitlines()):
                    raise ValueError("Shorten runbook commands before PDF export; do not silently wrap shell lines")
                story.append(KeepTogether([Preformatted(content, CODE)]))
                code.clear()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
        elif line.startswith("# "):
            flush()
            story.append(Paragraph(inline(line[2:]), H1))
        elif line.startswith("## "):
            flush()
            story.append(Paragraph(inline(line[3:]), H1))
        elif line.startswith("### "):
            flush()
            story.append(Paragraph(inline(line[4:]), H2))
        elif not line.strip():
            flush()
        else:
            paragraph.append(line)
    flush()
    if in_code:
        raise ValueError("Unclosed runbook code fence")
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, rightMargin=42, leftMargin=42,
                            topMargin=42, bottomMargin=53, title="CogniSight - next execution steps",
                            author="Jahnvi", subject="Simple laptop, Pi and phone setup procedure")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    main()
