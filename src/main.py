import os
import json
import typer
import gradio as gr
from dotenv import load_dotenv
from .crew import run

load_dotenv()
app = typer.Typer(add_completion=False)


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


@app.command()
def ui():
    def _build(topic, weeks, lessons_per_week, min_resources, cc_by, cc_by_sa, cc0, pub_domain):
        allow_list = []
        if cc_by: allow_list.append("CC-BY")
        if cc_by_sa: allow_list.append("CC-BY-SA")
        if cc0: allow_list.append("CC0")
        if pub_domain: allow_list.append("Public Domain")
        allow = ",".join(allow_list)
        res = run(topic, int(weeks), int(lessons_per_week), int(min_resources), allow)

        man = res.get("manifest", {})
        import os, json
        lessons = [p if p.startswith("course/") else os.path.join("course", p).replace("\\", "/")
                   for p in man.get("lessons", [])]
        quizzes = [q.replace("\\", "/") for q in man.get("quizzes", [])]
        syllabus = man.get("syllabus_md", "course/syllabus.md").replace("\\", "/")
        reading = man.get("reading_list", "course/reading_list.md").replace("\\", "/")
        manifest_path = "course/course_manifest.json"
        qa_path = "course/qa_report.json"
        key_files = [p for p in [syllabus, reading, manifest_path, qa_path] if os.path.exists(p)]
        # return: we only show files, not the JSON panes anymore
        return key_files, lessons, quizzes

    theme = gr.themes.Soft(primary_hue="indigo", neutral_hue="slate")
    with gr.Blocks(title="curate2course", theme=theme, fill_height=True, css="""
    .brandbar{display:flex;gap:8px;align-items:center;margin:.5rem 0 1rem}
    .brandbar .ico{
        font-size:22px;line-height:1;
        border:1px solid rgba(255,255,255,.18);
        padding:.35rem .5rem;border-radius:10px;
        background:rgba(120,120,255,.08);
        box-shadow:0 2px 8px rgba(0,0,0,.25)
    }
    .brandbar .brand{margin-left:.5rem;font-weight:700;font-size:18px;opacity:.95}
    .left-panel{min-width:420px}
    """) as demo:
        with gr.Row():
            with gr.Column(scale=1):
                with gr.Row(elem_classes="header-icons"):
                    gr.HTML("""
                        <div class="brandbar">
                        <span class="ico" title="Assemble">📦</span>
                        <span class="ico" title="Reason">🧠</span>
                        <span class="ico" title="Readings">📚</span>
                        <span class="brand">curate2course</span>
                        </div>
                        """)
                gr.Markdown("### curate2course")

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

            with gr.Column(scale=7, elem_id="results"):
                with gr.Tabs():
                    with gr.Tab("Key files"):
                        key_files = gr.Files(label="Syllabus, reading list, manifest, QA")
                    with gr.Tab("Lessons"):
                        lesson_files = gr.Files(label="Lesson markdown files")
                    with gr.Tab("Quizzes"):
                        quiz_files = gr.Files(label="Quiz JSON files")

        build_btn.click(
            _build,
            [topic, weeks, lessons, minres, cc_by, cc_by_sa, cc0, pub_domain],
            [key_files, lesson_files, quiz_files]
        )

    demo.queue().launch(show_api=False, server_name="127.0.0.1", server_port=7860)



if __name__ == "__main__":
    app()
