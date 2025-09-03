from pathlib import Path
import json
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    ListFlowable, ListItem, PageBreak
)
from reportlab.lib import colors
import re

class ExportTools:
    def write_text(self, path: str, content: str):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def write_json(self, path: str, obj):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---------- helpers ----------
    def _para(self, txt: str, style):
        """
        Build a safe ReportLab Paragraph by HTML-escaping and converting newlines to <br/>.
        This prevents ReportLab 'paraparser: unclosed tag' errors on raw text.
        """
        if txt is None:
            txt = ""
        safe = escape(str(txt)).replace("\r", "").replace("\t", "    ").replace("\n", "<br/>")
        return Paragraph(safe, style)

    # ---------- Markdown(ish) -> PDF ----------
    def write_pdf_from_markdown(self, md_text: str, out_path: str, title: str | None = None):
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        styles = getSampleStyleSheet()
        h1 = styles["Heading1"]; h1.spaceAfter = 8
        h2 = styles["Heading2"]; h2.spaceAfter = 6
        h3 = styles["Heading3"]; h3.spaceAfter = 4
        body = styles["BodyText"]; body.spaceAfter = 4

        doc = SimpleDocTemplate(
            str(out),
            pagesize=LETTER,
            leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
        )
        story = []

        if title:
            story.append(self._para(title, styles["Title"]))
            story.append(Spacer(1, 0.20 * inch))

        # Simple markdown-ish parsing with safe paragraphs and real lists
        lines = (md_text or "").splitlines()
        list_buffer: list[str] = []
        list_kind: str | None = None  # "bullet" | "number" | None

        import re
        num_re = re.compile(r"^\s*\d+\.\s+")

        def flush_list():
            nonlocal list_buffer, list_kind
            if not list_buffer:
                return
            items = [ListItem(self._para(li, body)) for li in list_buffer]
            lf_kwargs = {"leftIndent": 18}
            if list_kind == "number":
                lf_kwargs.update(dict(bulletType="1", start="1"))
            else:
                lf_kwargs.update(dict(bulletType="bullet"))
            story.append(ListFlowable(items, **lf_kwargs))
            story.append(Spacer(1, 0.08 * inch))
            list_buffer = []
            list_kind = None

        for raw in lines:
            line = (raw or "").rstrip()
            if not line:
                flush_list()
                story.append(Spacer(1, 0.08 * inch))
                continue

            if line.startswith("# "):
                flush_list()
                story.append(self._para(line[2:].strip(), h1))
                continue
            if line.startswith("## "):
                flush_list()
                story.append(self._para(line[3:].strip(), h2))
                continue
            if line.startswith("### "):
                flush_list()
                story.append(self._para(line[4:].strip(), h3))
                continue

            if line.lstrip().startswith("- "):
                kind = "bullet"
                txt = line.lstrip()[2:].strip()
                if list_kind not in (None, kind):
                    flush_list()
                list_kind = kind
                list_buffer.append(txt)
                continue

            if num_re.match(line):
                kind = "number"
                txt = num_re.sub("", line).strip()
                if list_kind not in (None, kind):
                    flush_list()
                list_kind = kind
                list_buffer.append(txt)
                continue

            # Normal paragraph
            flush_list()
            story.append(self._para(line, body))

        flush_list()
        doc.build(story)

    # ---------- Quiz JSON -> nicely formatted PDF ----------
    def quiz_json_to_pdf(self, quiz: dict, out_path: str, title: str | None = None):
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        styles = getSampleStyleSheet()
        h2 = styles["Heading2"]; h2.spaceAfter = 6
        h3 = styles["Heading3"]; h3.spaceAfter = 4
        body = styles["BodyText"]; body.spaceAfter = 4

        doc = SimpleDocTemplate(
            str(out),
            pagesize=LETTER,
            leftMargin=54, rightMargin=54, topMargin=54, bottomMargin=54,
        )
        story = []

        if title:
            story.append(self._para(title, styles["Title"]))
            story.append(Spacer(1, 0.20 * inch))

        items = (quiz or {}).get("items", []) or []
        alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

        for i, it in enumerate(items, 1):
            qtype = str(it.get("type", "mcq")).lower()

            if qtype in ("mcq", "multiple_choice", "choice"):
                story.append(self._para(f"Q{i}. {it.get('question','')}", h3))

                # Choices as a bulleted list (letters embedded in text)
                choices = it.get("choices", []) or []
                li = []
                for idx, ch in enumerate(choices):
                    label = f"{alpha[idx % 26]}) "
                    li.append(ListItem(self._para(label + str(ch), body)))
                if li:
                    story.append(ListFlowable(li, bulletType="bullet", leftIndent=18))

                story.append(self._para(f"Answer: {it.get('answer','')}", body))
                if it.get("rationale"):
                    story.append(self._para(f"Why: {it['rationale']}", body))

                meta_bits = []
                if it.get("bloom"):
                    meta_bits.append(f"Bloom: {it['bloom']}")
                if it.get("difficulty"):
                    meta_bits.append(f"Difficulty: {it['difficulty']}")
                if meta_bits:
                    story.append(self._para(" | ".join(meta_bits), body))

                story.append(Spacer(1, 0.15 * inch))

            else:
                # short-answer
                story.append(self._para(f"Short-answer: {it.get('prompt','')}", h3))
                story.append(Spacer(1, 0.15 * inch))

        doc.build(story)