import json
from openai import OpenAI

def llm_make_quiz(lesson_title: str, objectives: list[str], lesson_notes: str, model: str = "gpt-4o-mini") -> dict:
    client = OpenAI()
    sys = "You generate rigorous assessments aligned to objectives. Return ONLY strict JSON."
    usr = f"""
Create exactly 5 multiple-choice items and 1 short-answer item for this lesson.

Title: {lesson_title}
Objectives: {objectives}
Notes: {lesson_notes}

Rules:
- For MCQs, choices must be plain text without letter prefixes.
- The field "answer" must be a 0-based integer index into "choices".
- Include a non-empty "rationale" for every MCQ.
- "bloom" must be one of: remember, understand, apply, analyze, evaluate, create.
- "difficulty" must be one of: easy, medium, hard.
- Return only JSON.

Schema:
{{
  "items": [
    {{"type":"mcq","question":"...","choices":["...","...","...","..."],"answer":0,"rationale":"...","bloom":"understand","difficulty":"medium"}},
    ... four more MCQs ...,
    {{"type":"short","prompt":"..."}}
  ]
}}
"""
    r = client.chat.completions.create(
        model=model,
        messages=[{"role":"system","content":sys},{"role":"user","content":usr}],
        temperature=0.2,
        response_format={"type":"json_object"}
    )
    return json.loads(r.choices[0].message.content)
