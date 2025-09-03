from pathlib import Path
import json
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem
from reportlab.lib.units import inch

class ExportTools:
    def write_text(self, path: str, content: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def write_json(self, path: str, obj):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

    # same function you already had (kept; signature is md_text, out_path!)
    def write_pdf_from_markdown(self, md_text: str, out_path: str, title: str | None = None):
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(str(out), pagesize=LETTER, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        story = []
        if title:
            story.append(Paragraph(title, styles["Title"]))
            story.append(Spacer(1, 0.25 * inch))

        lines = md_text.splitlines()
        bullet_buf = []

        def flush_bullets():
            nonlocal story, bullet_buf
            if bullet_buf:
                items = [ListItem(Paragraph(x, styles["BodyText"])) for x in bullet_buf]
                story.append(ListFlowable(items, bulletType="bullet", start="bullet"))
                story.append(Spacer(1, 0.10 * inch))
                bullet_buf.clear()

        for line in lines:
            if line.startswith("# "):
                flush_bullets(); story.append(Paragraph(line[2:].strip(), styles["Heading1"])); story.append(Spacer(1, 0.10 * inch))
            elif line.startswith("## "):
                flush_bullets(); story.append(Paragraph(line[3:].strip(), styles["Heading2"])); story.append(Spacer(1, 0.08 * inch))
            elif line.startswith("### "):
                flush_bullets(); story.append(Paragraph(line[4:].strip(), styles["Heading3"])); story.append(Spacer(1, 0.06 * inch))
            elif line.strip().startswith("- "):
                bullet_buf.append(line.strip()[2:].strip())
            elif line.strip() == "":
                flush_bullets(); story.append(Spacer(1, 0.08 * inch))
            else:
                flush_bullets(); story.append(Paragraph(line.strip(), styles["BodyText"])); story.append(Spacer(1, 0.04 * inch))
        flush_bullets()
        doc.build(story)

    # NEW: quiz JSON → pretty PDF
    def write_quiz_pdf(self, quiz_obj: dict, out_path: str, title: str = "Quiz"):
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        styles = getSampleStyleSheet()
        h1 = styles["Heading1"]
        h2 = styles["Heading2"]
        p  = styles["BodyText"]
        code = ParagraphStyle('code', parent=p, fontName='Courier', leading=12)

        doc = SimpleDocTemplate(str(out), pagesize=LETTER, leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54)
        story = [Paragraph(title, h1), Spacer(1, 0.2*inch)]

        items = quiz_obj.get("items", [])
        for idx, q in enumerate(items, start=1):
            if q.get("type", "").lower() == "short":
                story.append(Paragraph(f"{idx}. (Short) {q.get('prompt','')}", h2))
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("Answer:", p))
                story.append(Spacer(1, 0.25*inch))
                story.append(Spacer(1, 0.25*inch))
                continue

            # MCQ
            story.append(Paragraph(f"{idx}. {q.get('question','')}", h2))
            choices = q.get("choices", [])
            bullets = [ListItem(Paragraph(c, p)) for c in choices]
            story.append(ListFlowable(bullets, bulletType='bullet', start='bullet'))
            story.append(Spacer(1, 0.05*inch))
            # teacher key (small)
            ans = q.get("answer", "")
            rationale = q.get("rationale", "")
            story.append(Paragraph(f"<i>Answer:</i> {ans}", p))
            if rationale:
                story.append(Paragraph(f"<i>Rationale:</i> {rationale}", p))
            story.append(Spacer(1, 0.15*inch))

        doc.build(story)
