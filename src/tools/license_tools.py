from typing import Iterable

DEFAULT_ALLOWED = {"CC-BY", "CC-BY-SA", "CC0", "Public Domain"}

def classify_license(text: str) -> str:
    t = text.lower()
    if "public domain" in t:
        return "Public Domain"
    if "cc0" in t:
        return "CC0"
    if "cc by-sa" in t or "cc-by-sa" in t or "cc by sa" in t:
        return "CC-BY-SA"
    if "cc by" in t or "cc-by" in t:
        return "CC-BY"
    return "Unknown"

class LicenseTools:
    def check(self, meta: str, allowlist: Iterable[str] | None = None) -> dict:
        allow = set(allowlist) if allowlist else DEFAULT_ALLOWED
        lic = classify_license(meta or "")
        ok = lic in allow
        return {"license": lic, "status": "OK" if ok else "VIOLATION"}
