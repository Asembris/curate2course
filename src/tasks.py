from crewai import Task
from pathlib import Path
from textwrap import dedent


def _prompt(name: str) -> str:
    p = Path(__file__).resolve().parents[1] / "configs" / "prompts" / f"{name}.md"
    if p.exists():
        t = p.read_text(encoding="utf-8").strip()
        if t:
            return t
    return f"{name} task."

def t_curate(agent, topic: str, allowlist: str):
    d = _prompt("curate") + f"\nTopic: {topic}\nAllowed licenses: {allowlist}\nOutput: brief notes."
    return Task(description=d, expected_output="curation notes", agent=agent)

def t_syllabus(agent, topic: str, weeks: int, lessons_per_week: int):
    d = _prompt("syllabus") + f"\nTopic: {topic}\nWeeks: {weeks}\nLessons/week: {lessons_per_week}\nOutput: brief syllabus outline."
    return Task(description=d, expected_output="syllabus outline", agent=agent)

def t_summarize(agent):
    d = _prompt("summarize") + "\nOutput: short notes plan."
    return Task(description=d, expected_output="notes plan", agent=agent)

def t_quiz(agent):
    d = _prompt("quiz") + "\nOutput: short assessment plan."
    return Task(description=d, expected_output="assessment plan", agent=agent)

def t_assemble(agent):
    d = _prompt("assemble") + "\nOutput: publishing checklist."
    return Task(description=d, expected_output="publishing checklist", agent=agent)

def t_qa(agent):
    d = _prompt("qa") + "\nOutput: QA checklist."
    return Task(description=d, expected_output="qa checklist", agent=agent)


def t_refine(agent, topic: str, weeks: int, lessons_per_week: int):
    total = max(1, weeks * lessons_per_week)
    desc = dedent(f"""
    Reformulate the user's topic into a focused course spec for open-education resources.

    Return STRICT JSON with this schema (and nothing else):
    {{
      "title": "Concise course title",
      "level": "intro|intermediate|advanced",
      "audience": "one sentence on target audience",
      "scope": "3-5 sentences describing the scope and boundaries",
      "global_objectives": ["...","...","..."],
      "subtopics": ["ordered lesson-sized subtopics, at least {total} items"],
      "keywords": ["search keywords", "...", "..."]
    }}

    Guidelines:
    - Subtopics must be concrete lesson themes (not duplicates, not just the same term).
    - Prefer widely-taught foundational coverage before niche items.
    - Avoid ambiguous or overlapping wording.
    - Use professional course language; no marketing copy.

    User topic: "{topic}"
    Weeks: {weeks}, Lessons per week: {lessons_per_week}
    """).strip()

    return Task(
        description=desc,
        expected_output="A valid JSON object exactly matching the schema.",
        agent=agent
    )