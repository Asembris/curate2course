import re, json

VALID_BLOOM = {"remember","understand","apply","analyze","evaluate","create"}
VALID_DIFF  = {"easy","medium","hard"}

def _strip_prefix(s: str) -> str:
    return re.sub(r"^\s*[A-Da-d]\)?\s*[\.\)]?\s*", "", s).strip()

def _answer_to_index(ans, choices):
    if isinstance(ans, int):
        return ans
    if isinstance(ans, str):
        s = ans.strip().lower()
        if len(s) == 1 and s in "abcd":
            return "abcd".index(s)
        m = re.match(r"([a-d])\)", s)
        if m:
            return "abcd".index(m.group(1))
        for i, c in enumerate(choices):
            if s == c.strip().lower():
                return i
    return 0

def normalize_quiz(q: dict) -> dict:
    items = q.get("items", [])
    out = []
    mcq_count = 0
    for it in items:
        if it.get("type") == "mcq":
            ch = [ _strip_prefix(x) for x in (it.get("choices") or []) ]
            ch = ch[:4] if len(ch) >= 4 else (ch + ["Option"]*(4-len(ch)))[:4]
            ans = _answer_to_index(it.get("answer"), ch)
            bloom = str(it.get("bloom","understand")).lower()
            diff  = str(it.get("difficulty","medium")).lower()
            bloom = bloom if bloom in VALID_BLOOM else "understand"
            diff  = diff if diff in VALID_DIFF else "medium"
            out.append({
                "type":"mcq",
                "question": it.get("question","").strip(),
                "choices": ch,
                "answer": int(ans),
                "rationale": it.get("rationale",""),
                "bloom": bloom,
                "difficulty": diff
            })
            mcq_count += 1
        elif it.get("type") == "short":
            out.append({"type":"short","prompt": it.get("prompt","").strip()})
    # enforce 5 mcqs + 1 short if possible
    out_mcq = [x for x in out if x["type"]=="mcq"][:5]
    out_short = [x for x in out if x["type"]=="short"]
    if not out_short:
        out_short = [{"type":"short","prompt":"Write a brief summary connecting one objective to an example."}]
    return {"items": out_mcq + out_short[:1]}
