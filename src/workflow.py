from pathlib import Path
from typing import Dict, List, Optional, Callable
from crewai import Crew, Process, Task
import wikipedia
import json, shutil

from .agents import supervisor, curator, designer, note_maker, assessor, assembler, auditor, topic_refiner
from .tasks import t_curate, t_syllabus, t_summarize, t_quiz, t_assemble, t_qa, t_refine
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


def _fallback_spec(topic: str, total_lessons: int) -> Dict:
    # deterministic spec if LLM fails: repeat-safe, simple spread of subtopics
    base = topic.strip().rstrip(".")
    seeds = [
        f"Introduction to {base}",
        f"Core concepts of {base}",
        f"Key terminology in {base}",
        f"Applications of {base}",
        f"Methods and techniques in {base}",
        f"Case studies in {base}",
        f"Current trends in {base}",
        f"Ethics and risks in {base}",
        f"Tools and resources for {base}",
        f"Review and synthesis of {base}",
    ]
    subtopics = (seeds * ((total_lessons // len(seeds)) + 1))[:total_lessons]
    return {
        "title": base.title(),
        "level": "intro",
        "audience": "Learners new to the topic.",
        "scope": f"A focused introduction to {base}, emphasizing fundamental ideas and typical use-cases.",
        "global_objectives": [
            f"Explain core ideas of {base}",
            f"Apply basic terminology of {base}",
            "Answer formative questions from readings"
        ],
        "subtopics": subtopics,
        "keywords": [base]
    }


def _run_topic_refiner(raw_topic: str, weeks: int, lessons_per_week: int) -> Dict:
    total = max(1, weeks * lessons_per_week)
    A_ref = topic_refiner()
    T_ref = t_refine(A_ref, raw_topic, weeks, lessons_per_week)
    crew = Crew(agents=[A_ref], tasks=[T_ref], process=Process.sequential, verbose=False)
    _ = crew.kickoff()

    raw = getattr(T_ref.output, "raw", T_ref.output)
    try:
        spec = json.loads(raw) if isinstance(raw, str) else raw
        # light validation
        if not isinstance(spec, dict) or "subtopics" not in spec or not spec["subtopics"]:
            raise ValueError("invalid spec")
        # ensure we have enough subtopics
        if len(spec["subtopics"]) < total:
            extra = _fallback_spec(raw_topic, total)["subtopics"]
            spec["subtopics"] = (spec["subtopics"] + extra)[:total]
        return spec
    except Exception:
        return _fallback_spec(raw_topic, total)


def _deterministic_build(
    topic: str,
    weeks: int,
    lessons_per_week: int,
    allow,
    qz_agent,
    progress_cb: Optional[Callable[[str, float], None]] = None,
    lesson_titles: Optional[List[str]] = None
) -> Dict:
    if progress_cb:
        progress_cb("Initializing build", 0.02)

    # Clean previous runs to avoid stale files / duplicates
    shutil.rmtree("course", ignore_errors=True)
    Path("course").mkdir(parents=True, exist_ok=True)

    st, lt, xt, tt = SearchTools(), LicenseTools(), ExportTools(), TextTools()

    total = max(1, weeks * lessons_per_week)

    if progress_cb:
        progress_cb("Searching open content", 0.06)
    seeds = st.wiki_search(topic, max_results=max(5, total + 3))

    if progress_cb:
        progress_cb("Filtering by license", 0.10)
    curated = []
    for it in seeds:
        meta = f"{it.get('title','')} CC-BY-SA"
        r = lt.check(meta, allow)
        if r["status"] == "OK":
            curated.append(
                {
                    "title": it["title"],
                    "url": it["url"],
                    "license": r["license"],
                    "source": it["source"],
                }
            )
    if not curated:
        curated = [
            {
                "title": topic,
                "url": f"https://en.wikipedia.org/wiki/{topic.replace(' ','_')}",
                "license": "CC-BY-SA",
                "source": "wikipedia",
            }
        ]

    # --- Syllabus ---
    if progress_cb:
        progress_cb("Constructing syllabus", 0.15)

    weeks_list = []
    k = 0
    titles_from_sources = [x["title"] for x in curated]

    total_needed = weeks * lessons_per_week

    refined_titles: Optional[List[str]] = None
    if isinstance(lesson_titles, list) and lesson_titles:
        refined_titles = [str(lesson_titles[i % len(lesson_titles)]) for i in range(total_needed)]

    for i in range(1, weeks + 1):
        lessons = []
        for _ in range(1, lessons_per_week + 1):
            k += 1
            if refined_titles:
                base_title = refined_titles[k - 1].strip()
            else:
                base_title = titles_from_sources[(k - 1) % len(titles_from_sources)]
            lessons.append({
                "lesson": k,
                "title": f"{topic}: {base_title}",
                "objectives": [
                    f"State key ideas of {base_title}",
                    f"Use terminology for {base_title}",
                    "Answer formative questions"
                ]
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
    syllabus_pdf = _pdfify(xt, syllabus_md, "syllabus.pdf", title=None)

    # --- Lessons ---
    if progress_cb:
        progress_cb("Authoring lessons", 0.22)

    lesson_md_paths: List[str] = []
    lesson_pdf_paths: List[str] = []
    k = 0
    total_lessons = weeks * lessons_per_week

    for w in syllabus["weeks"]:
        for l in w["lessons"]:
            k += 1
            src = curated[(k - 1) % len(curated)]

            # Pull Wikipedia content
            try:
                page = wikipedia.page(src["title"], auto_suggest=False)
                raw = tt.clean(page.content or "")
                summary = tt.dedupe_paragraphs(tt.clean(wikipedia.summary(src["title"], sentences=6)))
            except Exception:
                raw = summary = src["title"]

            # Try to build 3 "axes" from meaningful sections
            axes = []
            try:
                candidate_sections = [
                    "Overview",
                    "Introduction",
                    "Background",
                    "History",
                    "Principles",
                    "Types",
                    "Applications",
                    "Markets",
                    "Instruments",
                    "Risk",
                    "Regulation",
                    "Examples",
                    "Practice",
                ]
                seen = set()
                for name in candidate_sections:
                    try:
                        sec_txt = page.section(name)  # may NameError if page unset; caught by outer except
                    except Exception:
                        sec_txt = None
                    if sec_txt:
                        sec_txt = tt.dedupe_paragraphs(tt.clean(sec_txt.strip()))
                        # require a bit of substance
                        if len(sec_txt) > 250 and name not in seen:
                            axes.append((name, sec_txt))
                            seen.add(name)
                    if len(axes) >= 3:
                        break
            except Exception:
                pass

            # Fallback: split long paragraphs into 3 buckets
            if not axes:
                paras = [p.strip() for p in raw.split("\n") if len(p.strip()) > 80]
                if not paras:
                    paras = [p.strip() for p in raw.split("\n") if p.strip()]
                if not paras:
                    paras = [summary]
                # split into ~thirds
                third = max(1, len(paras) // 3)
                buckets = [paras[:third], paras[third : 2 * third], paras[2 * third :]]
                labels = ["Foundations", "Practice", "Implications"]
                for idx, bucket in enumerate(buckets):
                    if not bucket:
                        continue
                    axes.append((labels[idx], "\n\n".join(bucket[:5])))
                axes = axes[:3]

            # Key concepts = first sentences from summary + axes (max 5)
            key_concepts: List[str] = []

            def _first_sents(text: str, limit: int = 2) -> List[str]:
                sents = [s.strip() for s in text.split(". ") if s.strip()]
                picked = []
                for s in sents[:limit]:
                    if not s.endswith("."):
                        s += "."
                    picked.append(s)
                return picked

            key_concepts.extend(_first_sents(summary, limit=3))
            for _, txt in axes:
                if len(key_concepts) >= 5:
                    break
                key_concepts.extend(_first_sents(txt, limit=1))
                key_concepts = key_concepts[:5]

            attr = (
                f"{src['title']} — {src['license']} — {src['url']} — "
                "License: https://creativecommons.org/licenses/by-sa/4.0/"
            )

            self_check_lines = [
                f"1. Define {src['title']} in your own words.",
                f"2. List two applications or real-world examples of {src['title']}.",
                f"3. Explain one potential misconception about {src['title']} and correct it.",
            ]

            # Build lesson markdown (single H1 only)
            parts = []
            parts.append(f"# {l['title']}\n")
            parts.append("## Objectives\n" + "\n".join(f"- {o}" for o in l["objectives"]) + "\n")
            parts.append("## Overview\n" + summary + "\n")
            parts.append("## Key Concepts\n" + "\n".join(f"- {c}" for c in key_concepts) + "\n")
            parts.append("## Core Content")
            for idx, (name, text) in enumerate(axes, 1):
                parts.append(f"### {idx}. {name}\n{text}\n")
            parts.append("## Self-Check\n" + "\n".join(self_check_lines) + "\n")
            parts.append("## Attribution\n" + attr + "\n")
            md = "\n".join(parts)

            rel_md = f"lessons/week_{w['week']}/lesson_{l['lesson']}.md"
            rel_pdf = f"lessons/week_{w['week']}/lesson_{l['lesson']}.pdf"

            # Write MD + PDF (avoid duplicate title in the PDF: title=None)
            xt.write_text(f"course/{rel_md}", md)
            xt.write_pdf_from_markdown(md, f"course/{rel_pdf}", title=None)

            lesson_md_paths.append(f"course/{rel_md}")
            lesson_pdf_paths.append(f"course/{rel_pdf}")

            # ----- Quiz per lesson: JSON + pretty PDF -----
            payload = {
                "title": l["title"],
                "objectives": l["objectives"],
                "notes": (summary + "\n\n" + "\n\n".join(t for _, t in axes))[:3500],
            }
            quiz_task = Task(
                description=(
                    "Generate 5 MCQs and 1 short-answer aligned to the lesson. "
                    "Return ONLY strict JSON with fields: "
                    "items[{type,question,choices,answer,rationale,bloom,difficulty},"
                    "{type:'short',prompt}] "
                    f"Title: {payload['title']} Objectives: {payload['objectives']} Notes: {payload['notes']}"
                ),
                expected_output="Strict JSON object matching the schema.",
                agent=qz_agent,
            )
            Crew(agents=[qz_agent], tasks=[quiz_task], process=Process.sequential, verbose=False).kickoff()
            raw_out = getattr(quiz_task.output, "raw", quiz_task.output)
            try:
                quiz_json = json.loads(raw_out) if isinstance(raw_out, str) else raw_out
            except Exception:
                quiz_json = llm_make_quiz(payload["title"], payload["objectives"], payload["notes"])
            quiz_json = normalize_quiz(quiz_json)

            qjson_path = f"course/quizzes/week_{w['week']}_lesson_{l['lesson']}.json"
            qpdf_path = f"course/quizzes/week_{w['week']}_lesson_{l['lesson']}.pdf"
            xt.write_json(qjson_path, quiz_json)
            try:
                xt.quiz_json_to_pdf(quiz_json, qpdf_path, title=f"Quiz – {l['title']}")
            except Exception:
                pass

            if progress_cb:
                progress_cb(
                    f"Authoring lessons ({k}/{total_lessons})", 0.22 + 0.6 * (k / max(1, total_lessons))
                )

    # --- Reading list ---
    if progress_cb:
        progress_cb("Writing reading list", 0.85)
    reading_md = "# Reading List\n" + "\n".join(
        [f"- {it['title']} — {it['license']} — {it['url']}" for it in curated]
    )
    xt.write_text("course/reading_list.md", reading_md)
    reading_pdf = _pdfify(xt, reading_md, "reading_list.pdf", title=f"{topic} — Reading List")

    # --- Manifest + QA ---
    if progress_cb:
        progress_cb("Indexing quizzes", 0.90)
    quiz_json_files = sorted([p.as_posix() for p in Path("course/quizzes").glob("*.json")])
    quiz_pdf_files = sorted([p.as_posix() for p in Path("course/quizzes").glob("*.pdf")])

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
        "licenses": sorted(list(allow)),
    }
    xt.write_json("course/course_manifest.json", manifest)

    if progress_cb:
        progress_cb("QA: license check", 0.94)
    qa = {"license_violations": []}
    for it in curated:
        chk = lt.check(f"{it['title']} {it['license']}", allow)
        if chk["status"] != "OK":
            qa["license_violations"].append(it)
    xt.write_json("course/qa_report.json", qa)

    if progress_cb:
        progress_cb("Done", 1.0)
    return {"manifest": manifest, "qa": qa}

def run_pipeline(
    topic: str,
    weeks: int,
    lessons_per_week: int,
    min_resources: int,
    license_allowlist: str,
    cfg: Dict,
    fast_mode: bool = True,
    progress_cb: Optional[Callable[[str, float], None]] = None,
):
    allow = {x.strip() for x in license_allowlist.split(",")} if license_allowlist else DEFAULT_ALLOWED

    refined_topic = topic
    lesson_titles_from_refiner: Optional[List[str]] = None
    try:
        A_ref = topic_refiner()
        T_ref = t_refine(A_ref, topic, weeks, lessons_per_week)
        Crew(agents=[A_ref], tasks=[T_ref], process=Process.sequential, verbose=False).kickoff()

        _raw = getattr(T_ref.output, "raw", T_ref.output)
        _spec = json.loads(_raw) if isinstance(_raw, str) else (_raw or {})
        if isinstance(_spec, dict):
            # title
            refined_topic = _spec.get("title", topic) or topic
            # subtopics -> lesson titles (cycle/truncate to match #lessons)
            subs = _spec.get("subtopics")
            if isinstance(subs, list) and subs:
                total = max(1, weeks * lessons_per_week)
                lesson_titles_from_refiner = [str(subs[i % len(subs)]) for i in range(total)]
    except Exception:
        
        refined_topic = topic
        lesson_titles_from_refiner = None

    # ---- Regular crew agents / tasks ----
    A_sup = supervisor()
    A_cur = curator()
    A_des = designer()
    A_notes = note_maker()
    A_qz = assessor()
    A_asm = assembler()
    A_aud = auditor()

    T_cur = t_curate(A_cur, refined_topic, ", ".join(sorted(list(allow))))
    T_syl = t_syllabus(A_des, refined_topic, weeks, lessons_per_week)
    T_sum = t_summarize(A_notes)
    T_qz  = t_quiz(A_qz)
    T_asm = t_assemble(A_asm)
    T_qa  = t_qa(A_aud)

    Crew(
        agents=[A_cur, A_des, A_notes, A_qz, A_asm, A_aud],
        tasks=[T_cur, T_syl, T_sum, T_qz, T_asm, T_qa],
        process=Process.hierarchical,
        manager_agent=A_sup,
        verbose=False
    ).kickoff(inputs={"topic": refined_topic, "weeks": weeks, "lessons_per_week": lessons_per_week})


    built = _deterministic_build(
        refined_topic,
        weeks,
        lessons_per_week,
        allow,
        A_qz,
        progress_cb=progress_cb,
        lesson_titles=lesson_titles_from_refiner,
    )
    return {"status": "ok", "artifacts": ["course/"], "manifest": built["manifest"], "qa": built["qa"]}
