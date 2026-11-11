"""PDF version of a completed job's report (reportlab, pure Python)."""
import io, re, time
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

GREEN = colors.HexColor("#0b5d4b")

_MAP = {"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "\u2013", "\u2212": "-", "\u00a0": " ", "\u202f": " ", "\u2009": " ",
        "\u200b": "", "\u2248": "~", "\u2192": "->", "\u2265": ">=", "\u2264": "<="}

def _t(text) -> str:
    """Make text safe for the built-in PDF font (WinAnsi): map odd unicode, replace what is still unsupported."""
    t = "".join(_MAP.get(c, c) for c in str(text if text is not None else ""))
    return t.encode("cp1252", "replace").decode("cp1252")

def _md(text: str) -> str:
    """Tiny markdown -> reportlab markup (bold, bullets). Input is escaped first."""
    out = []
    for line in escape(_t(text or "")).splitlines():
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", line)
        m = re.match(r"^\s*(?:[-*•]|\d+\.)\s+(.*)", line)
        out.append(f"&bull; {m.group(1)}" if m else line)
    return "<br/>".join(out)

def build_pdf(job: dict, result: dict) -> bytes:
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=GREEN, fontSize=20, alignment=0, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=GREEN, fontSize=13, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=10, leading=14)
    small = ParagraphStyle("s", parent=body, fontSize=8, textColor=colors.grey)
    cell = ParagraphStyle("c", parent=body, fontSize=9, leading=11)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm,
                            title=f"BioQuote Report {job['id']}", author="BioQuote Agent")
    el = [Paragraph("BioQuote Agent &ndash; Analysis Report", h1),
          Paragraph("Quoted, billed (PayPal sandbox) and delivered automatically", small), Spacer(1, 6)]
    info = [["Job ID", job["id"]], ["Request", Paragraph(escape(_t(job["request"])), cell)],
            ["Job type", job["job_type"]], ["Amount", f"${job['amount_usd']:.2f} USD"],
            ["Status", job["status"].replace("_", " ")],
            ["Date", time.strftime("%d %b %Y %H:%M", time.localtime(job["created"]))]]
    t = Table(info, colWidths=[30*mm, 140*mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (0, -1), GREEN),
                           ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
    el.append(t)
    s = result.get("summary")
    if s:
        el.append(Paragraph("Summary", h2))
        types = ", ".join(f"{k}: {v}" for k, v in s["variant_types"].items())
        chroms = ", ".join(f"chr{k}: {v}" for k, v in s["top_chromosomes"].items())
        rows = [["Total variants", s["total_variants"]], ["Variant types", types], ["Ti/Tv ratio", s["ti_tv"] if s["ti_tv"] is not None else "n/a"],
                ["Most variants on", chroms], ["Matched in ClinVar-style table", s["annotated_with_clinvar"]],
                ["Flagged Pathogenic / Likely pathogenic", len(s["flagged_pathogenic"])]]
        t = Table([[a, Paragraph(escape(_t(b)), cell)] for a, b in rows], colWidths=[62*mm, 108*mm])
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
        el.append(t)
        fl = s["flagged_pathogenic"]
        if fl:
            el.append(Paragraph("Flagged variants", h2))
            data = [["Gene", "Position", "Change", "ClinVar", "Condition"]] + [
                [v["gene"], f"chr{v['chrom']}:{v['pos']}", f"{v['ref']}>{v['alt']}", v["clinvar"].replace("_", " "),
                 Paragraph(escape(_t(v["condition"])), cell)] for v in fl]
            t = Table(data, colWidths=[24*mm, 36*mm, 20*mm, 34*mm, 56*mm], repeatRows=1)
            t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GREEN), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                   ("FONTSIZE", (0, 0), (-1, -1), 9), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            el.append(t)
    el += [Paragraph("Report", h2), Paragraph(_md(result.get("report") or "No report available."), body), Spacer(1, 14),
           Paragraph("This is an automated research summary produced from public/synthetic demo data. It is not a clinical "
                     "diagnosis. Consult a clinical geneticist for interpretation. Generated by BioQuote Agent (MIT licensed).", small)]
    doc.build(el)
    return buf.getvalue()
