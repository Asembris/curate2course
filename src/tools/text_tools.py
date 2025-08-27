import re
from typing import List

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

def _sentences(text: str) -> List[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text.strip()) if s.strip()]

class TextTools:
    def clean(self, text: str) -> str:
        return re.sub(r"\s+", " ", text or " ").strip()

    def chunk(self, text: str, max_chars: int = 2000) -> List[str]:
        sents = _sentences(text or "")
        chunks, cur = [], ""
        for s in sents:
            if not cur:
                cur = s
            elif len(cur) + 1 + len(s) <= max_chars:
                cur += " " + s
            else:
                chunks.append(cur)
                cur = s
        if cur:
            chunks.append(cur)
        return chunks if chunks else [""]

    def dedupe_paragraphs(self, text: str) -> str:
        seen, out = set(), []
        for line in (text or "").splitlines():
            k = line.strip()
            if k and k not in seen:
                seen.add(k)
                out.append(line)
        return "\n".join(out)

    def readability(self, text: str) -> float:
        txt = self.clean(text or "")
        if not txt:
            return 0.0
        words = re.findall(r"\b\w+\b", txt)
        sents = max(1, len(_sentences(txt)))
        syll = sum(max(1, len(re.findall(r"[aeiouyAEIOUY]+", w))) for w in words)
        W = max(1, len(words))
        return 206.835 - 1.015 * (W / sents) - 84.6 * (syll / W)
