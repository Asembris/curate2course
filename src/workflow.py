from pathlib import Path
from typing import Dict, List, Optional, Callable
from crewai import Crew, Process, Task
import wikipedia
import json, shutil

from .agents import supervisor, curator, designer, note_maker, assessor, assembler, auditor
from .tasks import t_curate, t_syllabus, t_summarize, t_quiz, t_assemble, t_qa
from .tools.search_tools import SearchTools
from .tools.license_tools import LicenseTools, DEFAULT_ALLOWED
from .tools.export_tools import ExportTools
from .tools.text_tools import TextTools
from .tools.quiz_validate import normalize_quiz
from .tools.llm_tools import llm_make_quiz


def _pdfify(xt: ExportTools, md_text: str, rel_path_under_course: str, title: Optional[str] = None) -> str:
    """Create a PDF under course/ and return its course-relative path."""
    out_abs = (Path("course") / rel_path_under_course).as_posix()
    xt.write_pdf_from_markdown(md_text, out_abs, title=title)
    return f"course/{rel_path_under_course}"


def _deterministic_build(
    topic: str,
    weeks: int,
    lessons_per_week: int,
    allow,
    qz_agent,
    progress_cb: Optional[Callable[[str, float], None]] = None,
) -> Dict:
    if progress_cb: progress_cb("Initializing build", 0.02)

    # Clean previous runs to avoid stale files / duplicates
    shutil.rmtree("course", ignore_errors=True)
    Path("course").mkdir(parents=True, exist_ok=True)

    st, lt, xt, tt = SearchTools(), LicenseTools(), ExportTools(), TextTools()

    total = max(1, weeks * lessons_per_week)
    if progress_cb: progress_cb("Searching open content", 0.06)
    seeds = st.wiki_search(topic, max_results=max(5, total + 3))

    if progress_cb: progress_cb("Filtering by license", 0.10)
    curated = []
    for it in seeds:
        meta = f"{it.get('title','')} CC-BY-SA"
        r = lt.check(meta, allow)
        if r["status"] == "OK":
            curated.append({"title": it["title"], "url": it["url"], "license": r["license"], "source": it["source"]})
    if not curated:
        curated = [{"title": topic, "url": f"https://en.wikipedia.org/wiki/{topic.replace(' ','_')}", "license": "CC-BY-SA", "source": "wikipedia"}]

    if progress_cb: progress_cb("Constructing syllabus", 0.15)
    weeks_list, titles = [], [x["title"] for x in curated]
    k = 0
    for i in range(1, weeks + 1):
        lessons = []
        for _ in range(1, lessons_per_week + 1):
            k += 1
            tsel = titles[(k - 1) % len(titles)]
            lessons.append({
                "lesson": k,
                "title": f"{topic}: {tsel}",
                "objectives": [f"State key ideas of {tsel}", f"Use terminology for {tsel}", "Answer formative questions"]
            })
        weeks_list.append({"week": i, "lessons": lessons})
    syllabus = {"topic": topic, "weeks": weeks_list}

    xt.write_json("course/syllabus.json", syllabus)
    syllabus_md = (
        f"# {topic}\n"
        + "\n".join(
            [
                f"## Week {w['week']}\n" + "\n".join([f"- {l['title']}" for l in w["lessons"]])
                for w in syllabus["weeks"]
            ]
        )
    )
    xt.write_text("course/syllabus.md", syllabus_md)
    syllabus_pdf = _pdfify(xt, syllabus_md, "syllabus.pdf", title=f"{topic} — Syllabus")

    # --- Lessons ---
    if progress_cb: progress_cb("Authoring lessons", 0.22)
    lesson_md_paths, lesson_pdf_paths = [], []
    k = 0
    for w in syllabus["weeks"]:
        for l in w["lessons"]:
            k += 1
            src = curated[(k - 1) % len(curated)]

            # unique content per lesson
            try:
                page = wikipedia.page(src["title"], auto_suggest=False)
                raw = tt.clean(page.content or "")
                # carve different slices per lesson index to avoid sameness
                paras = [p for p in raw.split("\n") if p.strip()]
                slice_start = (k * 3) % max(1, len(paras))  # rotate
                core = "\n\n".join(paras[slice_start:slice_start + 8]) or "\n\n".join(paras[:6])
                summary = wikipedia.summary(src["title"], sentences=6)
            except Exception:
                summary, core = src["title"], src["title"]

            attr = f"{src['title']} — {src['license']} — {src['url']} — License: https://creativecommons.org/licenses/by-sa/4.0/"
            self_check = (
                f"1. Define {src['title']} in your own words.\n"
                f"2. List two applications of {src['title']}.\n"
                f"3. Explain one potential misconception about {src['title']}."
            )

            md = (
                f"# {l['title']}\n\n"
                f"## Objectives\n" + "\n".join([f"- {o}" for o in l["objectives"]]) + "\n\n"
                f"## Overview\n{tt.dedupe_paragraphs(tt.clean(summary))}\n\n"
                f"## Core Content\n{core}\n\n"
                f"## Self-Check\n{self_check}\n\n"
                f"## Attribution\n{attr}\n"
            )

            rel_md = f"lessons/week_{w['week']}/lesson_{l['lesson']}.md"
            rel_pdf = f"lessons/week_{w['week']}/lesson_{l['lesson']}.pdf"

            xt.write_text(f"course/{rel_md}", md)
            _pdfify(xt, md, rel_pdf, title=l["title"])

            lesson_md_paths.append(f"course/{rel_md}")
            lesson_pdf_paths.append(f"course/{rel_pdf}")

            # Quiz per lesson: JSON + PDF
            payload = {"title": l["title"], "objectives": l["objectives"], "notes": (summary + "\n\n" + core)[:3500]}
            quiz_task = Task(
                description=("Generate 5 MCQs and 1 short-answer aligned to the lesson. "
                             "Return ONLY strict JSON with fields: items[{type,question,choices,answer,rationale,bloom,difficulty},"
                             "{type:'short',prompt}] "
                             f"Title: {payload['title']} Objectives: {payload['objectives']} Notes: {payload['notes']}"),
                expected_output="Strict JSON object matching the schema.",
                agent=qz_agent
            )
            Crew(agents=[qz_agent], tasks=[quiz_task], process=Process.sequential, verbose=False).kickoff()
            raw = getattr(quiz_task.output, "raw", quiz_task.output)
            try:
                quiz_json = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                quiz_json = llm_make_quiz(payload["title"], payload["objectives"], payload["notes"])
            quiz_json = normalize_quiz(quiz_json)

            qjson_path = f"course/quizzes/week_{w['week']}_lesson_{l['lesson']}.json"
            qpdf_path  = f"course/quizzes/week_{w['week']}_lesson_{l['lesson']}.pdf"
            xt.write_json(qjson_path, quiz_json)
            xt.write_quiz_pdf(quiz_json, qpdf_path, title=l["title"])

            if progress_cb:
                progress_cb(f"Authoring lessons ({k}/{weeks*lessons_per_week})", 0.22 + 0.6 * (k / max(1, weeks*lessons_per_week)))

    # --- Reading list ---
    if progress_cb: progress_cb("Writing reading list", 0.85)
    reading_md = "# Reading List\n" + "\n".join([f"- {it['title']} — {it['license']} — {it['url']}" for it in curated])
    xt.write_text("course/reading_list.md", reading_md)
    reading_pdf = _pdfify(xt, reading_md, "reading_list.pdf", title=f"{topic} — Reading List")

    # --- Manifest + QA ---
    if progress_cb: progress_cb("Indexing quizzes", 0.90)
    quiz_json_files = sorted([p.as_posix() for p in Path("course/quizzes").glob("*.json")])
    quiz_pdf_files  = sorted([p.as_posix() for p in Path("course/quizzes").glob("*.pdf")])

    manifest = {
        "topic": topic,
        "weeks": weeks,
        "lessons_per_week": lessons_per_week,
        "lessons": lesson_md_paths,
        "lesson_pdfs": lesson_pdf_paths,
        "quizzes": quiz_json_files,
        "quiz_pdfs": quiz_pdf_files,
        "syllabus_md": "course/syllabus.md",
        "syllabus_pdf": syllabus_pdf,
        "syllabus_json": "course/syllabus.json",
        "reading_list": "course/reading_list.md",
        "reading_list_pdf": reading_pdf,
        "licenses": sorted(list(allow))
    }
    xt.write_json("course/course_manifest.json", manifest)

    if progress_cb: progress_cb("QA: license check", 0.94)
    qa = {"license_violations": []}
    for it in curated:
        chk = lt.check(f"{it['title']} {it['license']}", allow)
        if chk["status"] != "OK":
            qa["license_violations"].append(it)
    xt.write_json("course/qa_report.json", qa)

    if progress_cb: progress_cb("Done", 1.0)
    return {"manifest": manifest, "qa": qa}


def run_pipeline(topic: str, weeks: int, lessons_per_week: int, min_resources: int,
                 license_allowlist: str, cfg: Dict, fast_mode: bool = True,
                 progress_cb: Optional[Callable[[str, float], None]] = None):
    allow = {x.strip() for x in license_allowlist.split(",")} if license_allowlist else DEFAULT_ALLOWED

    A_sup, A_cur, A_des, A_notes, A_qz, A_asm, A_aud = supervisor(), curator(), designer(), note_maker(), assessor(), assembler(), auditor()
    T_cur, T_syl, T_sum, T_qz, T_asm, T_qa = (
        t_curate(A_cur, topic, ", ".join(sorted(list(allow)))),
        t_syllabus(A_des, topic, weeks, lessons_per_week),
        t_summarize(A_notes),
        t_quiz(A_qz),
        t_assemble(A_asm),
        t_qa(A_aud),
    )
    Crew(agents=[A_cur, A_des, A_notes, A_qz, A_asm, A_aud], tasks=[T_cur, T_syl, T_sum, T_qz, T_asm, T_qa],
         process=Process.hierarchical, manager_agent=A_sup, verbose=False).kickoff(
        inputs={"topic": topic, "weeks": weeks, "lessons_per_week": lessons_per_week}
    )

    built = _deterministic_build(topic, weeks, lessons_per_week, allow, A_qz, progress_cb=progress_cb)
    return {"status": "ok", "artifacts": ["course/"], "manifest": built["manifest"], "qa": built["qa"]}
