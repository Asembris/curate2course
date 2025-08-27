from pathlib import Path
from typing import Dict, List
from crewai import Crew, Process, Task
import wikipedia
import json
from .agents import supervisor, curator, designer, note_maker, assessor, assembler, auditor
from .tasks import t_curate, t_syllabus, t_summarize, t_quiz, t_assemble, t_qa
from .tools.search_tools import SearchTools
from .tools.license_tools import LicenseTools, DEFAULT_ALLOWED
from .tools.export_tools import ExportTools
from .tools.text_tools import TextTools
from .tools.quiz_validate import normalize_quiz
from .tasks import *
from .tools.llm_tools import llm_make_quiz


def _deterministic_build(topic: str, weeks: int, lessons_per_week: int, allow, qz_agent) -> Dict:
    Path("course").mkdir(parents=True, exist_ok=True)
    st = SearchTools()
    lt = LicenseTools()
    xt = ExportTools()
    tt = TextTools()
    total = weeks * lessons_per_week
    seeds = st.wiki_search(topic, max_results=max(5, total))
    curated = []
    for it in seeds:
        meta = f"{it.get('title','')} CC-BY-SA"
        r = lt.check(meta, allow)
        if r["status"] == "OK":
            curated.append({"title": it["title"], "url": it["url"], "license": r["license"], "source": it["source"]})
    if not curated:
        curated = [{"title": topic, "url": f"https://en.wikipedia.org/wiki/{topic.replace(' ','_')}", "license": "CC-BY-SA", "source": "wikipedia"}]
    titles = [x["title"] for x in curated]
    weeks_list = []
    k = 0
    for i in range(1, weeks + 1):
        lessons = []
        for j in range(1, lessons_per_week + 1):
            k += 1
            t = titles[(k - 1) % len(titles)]
            lessons.append({"lesson": k, "title": f"{topic}: {t}", "objectives": [f"State key ideas of {t}", f"Use terminology for {t}", "Answer formative questions"]})
        weeks_list.append({"week": i, "lessons": lessons})
    syllabus = {"topic": topic, "weeks": weeks_list}
    xt.write_json("syllabus.json", syllabus)
    xt.write_text("syllabus.md", f"# {topic}\n" + "\n".join([f"## Week {w['week']}\n" + "\n".join([f"- {l['title']}" for l in w["lessons"]]) for w in syllabus["weeks"]]))
    lesson_paths: List[str] = []
    k = 0
    for w in syllabus["weeks"]:
        for l in w["lessons"]:
            k += 1
            title = l["title"]
            src = curated[(k - 1) % len(curated)]
            try:
                summary = wikipedia.summary(src["title"], sentences=6)
            except Exception:
                summary = src["title"]
            summary = tt.dedupe_paragraphs(tt.clean(summary))
            attr = f"{src['title']} — {src['license']} — {src['url']} — License: https://creativecommons.org/licenses/by-sa/4.0/"
            md = f"# {title}\n\n## Objectives\n" + "\n".join([f"- {o}" for o in l["objectives"]]) + "\n\n## Notes\n" + summary + f"\n\n## Attribution\n{attr}\n"
            path = f"lessons/week_{w['week']}/lesson_{l['lesson']}.md"
            xt.write_text(path, md)
            lesson_paths.append(path)
            payload = {
                "title": title,
                "objectives": l["objectives"],
                "notes": summary[:2500]
            }
            quiz_task = Task(
                description=(
                    "Generate 5 MCQs and 1 short-answer aligned to the lesson. "
                    "Return ONLY strict JSON with fields: items[{type,question,choices,answer,rationale,bloom,difficulty},...,{type:'short',prompt}].\n"
                    f"Title: {payload['title']}\nObjectives: {payload['objectives']}\nNotes: {payload['notes']}"
                ),
                expected_output="Strict JSON object matching the schema.",
                agent=qz_agent
            )
            quiz_crew = Crew(agents=[qz_agent], tasks=[quiz_task], process=Process.sequential, verbose=False)
            _ = quiz_crew.kickoff()
            raw = getattr(quiz_task.output, "raw", quiz_task.output)
            try:
                quiz_json = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                quiz_json = llm_make_quiz(payload["title"], payload["objectives"], payload["notes"])
            quiz_json = normalize_quiz(quiz_json)
            xt.write_json(f"quizzes/week_{w['week']}_lesson_{l['lesson']}.json", quiz_json)
    reading = [f"- {it['title']} — {it['license']} — {it['url']}" for it in curated]
    xt.write_text("reading_list.md", "# Reading List\n" + "\n".join(reading))
    quiz_files = sorted([p.as_posix() for p in Path("course/quizzes").glob("*.json")])
    manifest = {
        "topic": topic,
        "weeks": weeks,
        "lessons_per_week": lessons_per_week,
        "lessons": lesson_paths,
        "quizzes": quiz_files,
        "syllabus_md": "course/syllabus.md",
        "syllabus_json": "course/syllabus.json",
        "reading_list": "course/reading_list.md",
        "licenses": sorted(list(allow))
    }
    xt.write_json("course_manifest.json", manifest)
    qa = {"license_violations": []}
    for it in curated:
        chk = lt.check(f"{it['title']} {it['license']}", allow)
        if chk["status"] != "OK":
            qa["license_violations"].append(it)
    xt.write_json("qa_report.json", qa)
    return {"manifest": manifest, "qa": qa}

def run_pipeline(topic: str, weeks: int, lessons_per_week: int, min_resources: int, license_allowlist: str, cfg: Dict):
    allow = {x.strip() for x in license_allowlist.split(",")} if license_allowlist else DEFAULT_ALLOWED
    A_sup = supervisor()
    A_cur = curator()
    A_des = designer()
    A_notes = note_maker()
    A_qz = assessor()
    A_asm = assembler()
    A_aud = auditor()
    T_cur = t_curate(A_cur, topic, ", ".join(sorted(list(allow))))
    T_syl = t_syllabus(A_des, topic, weeks, lessons_per_week)
    T_sum = t_summarize(A_notes)
    T_qz = t_quiz(A_qz)
    T_asm = t_assemble(A_asm)
    T_qa = t_qa(A_aud)
    crew = Crew(
        agents=[A_cur, A_des, A_notes, A_qz, A_asm, A_aud],
        tasks=[T_cur, T_syl, T_sum, T_qz, T_asm, T_qa],
        process=Process.hierarchical,
        manager_agent=A_sup,
        verbose=True
    )
    _ = crew.kickoff(inputs={"topic": topic, "weeks": weeks, "lessons_per_week": lessons_per_week})
    built = _deterministic_build(topic, weeks, lessons_per_week, allow, A_qz)
    return {"status": "ok", "artifacts": ["course/"], "manifest": built["manifest"], "qa": built["qa"]}
