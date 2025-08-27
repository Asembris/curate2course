from crewai import Task
from pathlib import Path

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
