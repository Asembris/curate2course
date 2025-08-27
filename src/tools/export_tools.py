from pathlib import Path
import json

class ExportTools:
    def write_text(self, rel_path: str, text: str) -> str:
        p = Path("course") / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text or "", encoding="utf-8")
        return str(p)

    def write_json(self, rel_path: str, obj) -> str:
        p = Path("course") / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(p)
