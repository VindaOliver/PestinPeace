from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import gradio as gr
from ultralytics import YOLO


# Avoid localhost proxy hijacking in some Windows setups.
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

BASE_DIR = Path(__file__).resolve().parent


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="replace")


def find_run_dirs(base_dir: Path) -> list[Path]:
    run_dirs: dict[str, Path] = {}
    for best in base_dir.glob("runs/**/weights/best.pt"):
        run_dir = best.parent.parent
        run_dirs[str(run_dir)] = run_dir
    return sorted(run_dirs.values(), key=lambda p: p.stat().st_mtime, reverse=True)


def find_model_candidates(base_dir: Path) -> list[str]:
    models: list[Path] = []
    models.extend(base_dir.glob("*.pt"))
    models.extend(base_dir.glob("runs/**/weights/best.pt"))
    models.extend(base_dir.glob("runs/**/weights/last.pt"))

    seen: set[str] = set()
    out: list[str] = []
    for p in sorted(models, key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
        sp = str(p)
        if sp not in seen:
            seen.add(sp)
            out.append(sp)
    return out


def find_latest_best_pt(base_dir: Path) -> str:
    bests = sorted(base_dir.glob("runs/**/weights/best.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(bests[0]) if bests else ""


def _to_pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def refresh_model_choices():
    choices = find_model_candidates(BASE_DIR)
    default_value = find_latest_best_pt(BASE_DIR)
    if not default_value and choices:
        default_value = choices[0]
    return gr.update(choices=choices, value=default_value)


def predict_image(
    image_rgb,
    model_path: str,
    conf: float,
    iou: float,
    imgsz: int,
    max_det: int,
    device: str,
):
    if image_rgb is None:
        return None, "Please upload an image first.", "", ""
    if not model_path or not Path(model_path).exists():
        return None, f"Model file not found: {model_path}", "", ""

    model = YOLO(model_path)
    run_device = 0 if device == "gpu" else "cpu"

    results = model.predict(
        source=image_rgb,
        conf=float(conf),
        iou=float(iou),
        imgsz=int(imgsz),
        max_det=int(max_det),
        device=run_device,
        verbose=False,
    )

    r0 = results[0]
    boxes = r0.boxes
    count = 0 if boxes is None else len(boxes)

    conf_list: list[float] = []
    if boxes is not None and boxes.conf is not None:
        conf_list = [round(float(x), 4) for x in boxes.conf.detach().cpu().tolist()]

    plotted_bgr = r0.plot()
    plotted_rgb = cv2.cvtColor(plotted_bgr, cv2.COLOR_BGR2RGB)

    meta_text = "\n".join(
        [
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Model: {model_path}",
            f"Count: {count}",
            f"conf={conf}, iou={iou}, imgsz={imgsz}, max_det={max_det}, device={device}",
        ]
    )

    detail_payload = {
        "count": int(count),
        "confidence_list": conf_list,
        "mean_confidence": round(sum(conf_list) / len(conf_list), 4) if conf_list else None,
    }
    return plotted_rgb, f"Aphid count: {count}", meta_text, _to_pretty_json(detail_payload)


def refresh_runs():
    run_dirs = find_run_dirs(BASE_DIR)
    choices = [str(p) for p in run_dirs]
    default_value = choices[0] if choices else ""
    return gr.update(choices=choices, value=default_value)


def inspect_run(run_dir: str):
    if not run_dir:
        return "", "", "Please select a training run directory.", [], "No report found.", "No summary found.", "No context found.", "No CSV found."

    rd = Path(run_dir)
    if not rd.exists():
        return run_dir, "", f"Directory not found: {run_dir}", [], "No report found.", "No summary found.", "No context found.", "No CSV found."

    best_pt = rd / "weights" / "best.pt"
    summary_path = rd / "results_summary.json"
    context_path = rd / "train_context.json"
    report_path = rd / "presentation_report.md"
    csv_path = rd / "results.csv"

    summary_text = _read_text_if_exists(summary_path)
    context_text = _read_text_if_exists(context_path)
    report_text = _read_text_if_exists(report_path)
    csv_preview = ""
    if csv_path.exists():
        csv_lines = _read_text_if_exists(csv_path).splitlines()
        csv_preview = "\n".join(csv_lines[:15])

    image_candidates = [
        "results.png",
        "BoxPR_curve.png",
        "BoxP_curve.png",
        "BoxR_curve.png",
        "BoxF1_curve.png",
        "PR_curve.png",
        "P_curve.png",
        "R_curve.png",
        "F1_curve.png",
        "confusion_matrix.png",
        "confusion_matrix_normalized.png",
        "labels.jpg",
        "train_batch0.jpg",
        "train_batch1.jpg",
        "train_batch2.jpg",
        "val_batch0_pred.jpg",
        "val_batch0_labels.jpg",
    ]
    gallery = [str(rd / name) for name in image_candidates if (rd / name).exists()]

    run_info = "\n".join(
        [
            f"Run Dir: {run_dir}",
            f"Best Weight: {best_pt if best_pt.exists() else 'Not Found'}",
            f"Summary JSON: {summary_path if summary_path.exists() else 'Not Found'}",
            f"Context JSON: {context_path if context_path.exists() else 'Not Found'}",
        ]
    )

    report_display = report_text if report_text else "No presentation_report.md found."
    summary_display = summary_text if summary_text else "No results_summary.json found."
    context_display = context_text if context_text else "No train_context.json found."
    csv_display = csv_preview if csv_preview else "No results.csv found."

    return (
        run_dir,
        str(best_pt) if best_pt.exists() else "",
        run_info,
        gallery,
        report_display,
        summary_display,
        context_display,
        csv_display,
    )


def build_ui():
    model_choices = find_model_candidates(BASE_DIR)
    default_model = find_latest_best_pt(BASE_DIR)
    if not default_model and model_choices:
        default_model = model_choices[0]

    run_dirs = find_run_dirs(BASE_DIR)
    run_choices = [str(p) for p in run_dirs]
    default_run = run_choices[0] if run_choices else ""

    with gr.Blocks(title="Aphid Counter Dashboard") as demo:
        gr.Markdown(
            "# Aphid Counter Dashboard\n"
            "Use the first tab for aphid counting, and the second tab to visualize training metrics and plots."
        )

        with gr.Tab("Inference"):
            with gr.Row():
                with gr.Column(scale=1):
                    model_path = gr.Dropdown(
                        choices=model_choices,
                        value=default_model,
                        label="Model Path (.pt)",
                        allow_custom_value=True,
                    )
                    refresh_model_btn = gr.Button("Refresh Model List")
                    device = gr.Radio(["gpu", "cpu"], value="gpu", label="Device")
                    conf = gr.Slider(0.01, 0.90, value=0.25, step=0.01, label="conf")
                    iou = gr.Slider(0.10, 0.90, value=0.45, step=0.01, label="iou")
                    imgsz = gr.Slider(320, 1280, value=640, step=32, label="imgsz")
                    max_det = gr.Slider(1, 3000, value=1000, step=1, label="max_det")
                    img_in = gr.Image(label="Input Image", type="numpy")
                    run_btn = gr.Button("Run Detection")

                with gr.Column(scale=1):
                    img_out = gr.Image(label="Detected Image")
                    count_text = gr.Textbox(label="Count Result")
                    meta_text = gr.Textbox(label="Runtime Metadata", lines=6)
                    detail_json = gr.Code(label="Detection Detail (JSON)", language="json")

            refresh_model_btn.click(fn=refresh_model_choices, outputs=[model_path])
            run_btn.click(
                fn=predict_image,
                inputs=[img_in, model_path, conf, iou, imgsz, max_det, device],
                outputs=[img_out, count_text, meta_text, detail_json],
            )

        with gr.Tab("Training Visualization"):
            with gr.Row():
                with gr.Column(scale=1):
                    run_dir = gr.Dropdown(
                        choices=run_choices,
                        value=default_run,
                        label="Run Directory",
                        allow_custom_value=True,
                    )
                    refresh_run_btn = gr.Button("Refresh Runs")
                    inspect_btn = gr.Button("Load Run Artifacts")
                    run_info = gr.Textbox(label="Run Info", lines=6)
                    best_weight = gr.Textbox(label="Best Weight Path")

                with gr.Column(scale=2):
                    gallery = gr.Gallery(label="Training Plots", columns=3, height=420, object_fit="contain")
                    report_md = gr.Markdown(label="Presentation Report")

            with gr.Row():
                summary_json = gr.Code(label="results_summary.json", language="json")
                context_json = gr.Code(label="train_context.json", language="json")

            csv_preview = gr.Textbox(label="results.csv Preview (first 15 lines)", lines=15)

            refresh_run_btn.click(fn=refresh_runs, outputs=[run_dir])
            inspect_btn.click(
                fn=inspect_run,
                inputs=[run_dir],
                outputs=[run_dir, best_weight, run_info, gallery, report_md, summary_json, context_json, csv_preview],
            )

    return demo


if __name__ == "__main__":
    demo = build_ui()
    demo.launch(inbrowser=True, server_name="127.0.0.1", server_port=7860, share=False)
