import yaml
from pathlib import Path
from .workflow import run_pipeline

def load_config():
    p = Path(__file__).resolve().parents[1] / "configs" / "settings.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))

def run(topic, weeks, lessons_per_week, min_resources, license_allowlist):
    cfg = load_config()
    return run_pipeline(topic, int(weeks), int(lessons_per_week), int(min_resources), license_allowlist, cfg)
