import re
from typing import List, Dict
import wikipedia
from youtube_transcript_api import YouTubeTranscriptApi

_YT_PATTERNS = [
    re.compile(r"(?:v=)([A-Za-z0-9_\-]{11})"),
    re.compile(r"youtu\.be/([A-Za-z0-9_\-]{11})"),
    re.compile(r"youtube\.com/embed/([A-Za-z0-9_\-]{11})"),
]

def _extract_yt_id(s: str) -> str | None:
    for pat in _YT_PATTERNS:
        m = pat.search(s)
        if m:
            return m.group(1)
    return s if len(s) == 11 else None

class SearchTools:
    def wiki_search(self, query: str, max_results: int = 5) -> List[Dict]:
        try:
            titles = wikipedia.search(query, results=max_results)
            out = []
            for t in titles:
                try:
                    page = wikipedia.page(t, auto_suggest=False, redirect=True)
                    out.append({"title": page.title, "url": page.url, "source": "wikipedia"})
                except Exception:
                    continue
            return out
        except Exception:
            return []

    def youtube_transcript_text(self, url_or_id: str, languages: tuple[str, ...] = ("en",)) -> str:
        vid = _extract_yt_id(url_or_id)
        if not vid:
            return ""
        try:
            srt = YouTubeTranscriptApi.get_transcript(vid, languages=list(languages))
            return " ".join(x["text"] for x in srt if x.get("text"))
        except Exception:
            return ""
