import os, json, threading, queue, time
import typer
import gradio as gr
from dotenv import load_dotenv
from .crew import run

load_dotenv()
app = typer.Typer(add_completion=False)

try:
    import gradio_client.utils as _gcu
    _orig_get_type = _gcu.get_type
    def _safe_get_type(schema):
        if isinstance(schema, bool):
            return "any"
        return _orig_get_type(schema)
    _gcu.get_type = _safe_get_type

    _orig_json_to_py = _gcu._json_schema_to_python_type
    def _safe_json_to_py(schema, defs=None):
        if isinstance(schema, bool):
            return "any"
        return _orig_json_to_py(schema, defs)
    _gcu._json_schema_to_python_type = _safe_json_to_py
except Exception as _e:
    print("gradio-client patch skipped:", _e)


@app.command()
def build(
    topic: str = typer.Option(...),
    weeks: int = typer.Option(4),
    lessons_per_week: int = typer.Option(2),
    min_resources: int = typer.Option(2),
    license_allowlist: str = typer.Option("CC-BY,CC-BY-SA,CC0,Public Domain"),
):
    res = run(topic, weeks, lessons_per_week, min_resources, license_allowlist)
    typer.echo(json.dumps(res, indent=2))


def _gather_files(man):
    lessons = [p.replace("\\", "/") for p in man.get("lesson_pdfs", []) or man.get("lessons", [])]
    quizzes = [p.replace("\\", "/") for p in man.get("quiz_pdfs", []) or man.get("quizzes", [])]
    key = []
    # prefer PDFs if present
    if man.get("syllabus_pdf"): key.append(man["syllabus_pdf"])
    else: key.append(man.get("syllabus_md", "course/syllabus.md"))
    if man.get("reading_list_pdf"): key.append(man["reading_list_pdf"])
    else: key.append(man.get("reading_list", "course/reading_list.md"))
    key += ["course/course_manifest.json", "course/qa_report.json"]
    key = [p for p in key if os.path.exists(p)]
    return key, lessons, quizzes


@app.command()
def ui():
    def _build(topic, weeks, lessons_per_week, min_resources, cc_by, cc_by_sa, cc0, pub_domain):
        allow_list = []
        if cc_by: allow_list.append("CC-BY")
        if cc_by_sa: allow_list.append("CC-BY-SA")
        if cc0: allow_list.append("CC0")
        if pub_domain: allow_list.append("Public Domain")
        allow = ",".join(allow_list)

        # progress streaming via queue
        q = queue.Queue()
        status = {"msg": "Starting...", "pct": 0.0}
        def progress_cb(msg, pct):
            q.put(("progress", msg, float(pct)))

        result_holder = {"res": None, "done": False, "err": None}

        def worker():
            try:
                result_holder["res"] = run(topic, int(weeks), int(lessons_per_week), int(min_resources), allow, progress_cb=progress_cb)
            except Exception as e:
                result_holder["err"] = str(e)
            finally:
                result_holder["done"] = True

        t = threading.Thread(target=worker, daemon=True)
        t.start()

        # stream updates
        last_emit = 0
        while not result_holder["done"] or not q.empty():
            try:
                kind, msg, pct = q.get(timeout=0.1)
                if kind == "progress":
                    status["msg"], status["pct"] = msg, max(0, min(100, round(pct*100)))
            except queue.Empty:
                pass
            # throttle UI updates a bit
            now = time.time()
            if now - last_emit > 0.2:
                yield status["pct"], f"{status['msg']} — {status['pct']}%", [], [], []
                last_emit = now

        if result_holder["err"]:
            yield 0, f"❌ Build failed: {result_holder['err']}", [], [], []
            return

        man = (result_holder["res"] or {}).get("manifest", {})
        key_files, lesson_files, quiz_files = _gather_files(man)
        yield 100, "Done — 100%", key_files, lesson_files, quiz_files

    theme = gr.themes.Soft(primary_hue="indigo", neutral_hue="slate")
    with gr.Blocks(title="curate2course", theme=theme, fill_height=True, css="""
        .brandbar{display:flex;gap:8px;align-items:center;margin:.5rem 0 1rem}
        .brandbar .ico{font-size:22px;line-height:1;border:1px solid rgba(255,255,255,.18);padding:.35rem .5rem;border-radius:10px;background:rgba(120,120,255,.08);box-shadow:0 2px 8px rgba(0,0,0,.25)}
        .brandbar .brand{margin-left:.5rem;font-weight:700;font-size:18px;opacity:.95}
        .left-panel{min-width:420px}
    """) as demo:
        with gr.Row():
            with gr.Column(scale=1):
                gr.HTML("""
                    <div class="brandbar">
                      <span class="ico" title="Assemble">📦</span>
                      <span class="ico" title="Reason">🧠</span>
                      <span class="ico" title="Readings">📚</span>
                      <span class="brand">curate2course</span>
                    </div>
                """)

        with gr.Row(equal_height=True):
            with gr.Column(scale=5, elem_classes="left-panel"):
                topic = gr.Textbox(label="Topic")
                weeks = gr.Slider(1, 12, value=4, step=1, label="Weeks")
                lessons = gr.Slider(1, 7, value=2, step=1, label="Lessons per week")
                minres = gr.Slider(1, 5, value=2, step=1, label="Min resources per lesson")
                with gr.Accordion("Allowed licenses", open=False, elem_id="licenses"):
                    with gr.Row():
                        cc_by = gr.Checkbox(value=True, label="CC-BY")
                        cc_by_sa = gr.Checkbox(value=True, label="CC-BY-SA")
                        cc0 = gr.Checkbox(value=True, label="CC0")
                        pub_domain = gr.Checkbox(value=True, label="Public Domain")
                build_btn = gr.Button("Build Course", variant="primary")

                prog = gr.Slider(0, 100, value=0, step=1, label="Build progress", interactive=False)
                status_md = gr.Markdown("")

            with gr.Column(scale=7, elem_id="results"):
                with gr.Tabs():
                    with gr.Tab("Key files"):
                        key_files = gr.Files(label="Syllabus (PDF), Reading list (PDF), Manifest, QA")
                    with gr.Tab("Lessons"):
                        lesson_files = gr.Files(label="Lesson PDFs")
                    with gr.Tab("Quizzes"):
                        quiz_files = gr.Files(label="Quiz PDFs")

        
        build_btn.click(
            _build,
            [topic, weeks, lessons, minres, cc_by, cc_by_sa, cc0, pub_domain],
            [prog, status_md, key_files, lesson_files, quiz_files]
        )

    demo.queue().launch(show_api=False, server_name="127.0.0.1", server_port=7860)


if __name__ == "__main__":
    app()
