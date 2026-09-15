"""Streamlit UI test nhanh cho Label QA Agent (src/agents/graph.py).

Upload ảnh (+ file nhãn gốc tuỳ chọn), agent tự parse nhãn (nếu thiếu thì
tự đoán theo quy ước dataset), tự chạy YOLO (+ RT-DETR tuỳ chọn), rồi
hiển thị QA report.

Chạy: streamlit run app.py
"""

import asyncio
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

from src.agents.graph import agent
from src.agents.nodes.ensemble_flagging import flag_issues_ensemble
from src.agents.nodes.flagging import flag_issues
from src.agents.nodes.matching import match_labels
from src.config import get_settings

st.set_page_config(page_title="Label QA Agent", page_icon="🔍", layout="wide")

STATUS_STYLE = {
    "pass": ("✅ PASS", "green"),
    "needs_review": ("⚠️ NEEDS REVIEW", "orange"),
    "error": ("❌ ERROR", "red"),
}
SEVERITY_STYLE = {"high": "🔴 high", "medium": "🟠 medium", "low": "🟡 low"}
SEVERITY_COLOR = {"high": "red", "medium": "orange", "low": "gold"}


def _rect(draw: ImageDraw.ImageDraw, bbox: dict, color: str, width: int, text: str | None = None) -> None:
    draw.rectangle([bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]], outline=color, width=width)
    if text:
        draw.text((bbox["x1"] + 2, bbox["y1"] + 2), text, fill=color)


def draw_gt(image: Image.Image, gt_labels: list[dict]) -> Image.Image:
    """Ảnh gốc + nhãn gốc (ground truth) — xanh dương."""
    img = image.convert("RGB").copy()
    draw = ImageDraw.Draw(img)
    for gt in gt_labels or []:
        _rect(draw, gt["bbox"], "blue", 3, gt.get("class_name", "?"))
    return img


def draw_pred(image: Image.Image, pred_labels: list[dict], color: str = "lime") -> Image.Image:
    """Ảnh + danh sách prediction (dùng chung cho YOLO và RT-DETR — cùng format)."""
    img = image.convert("RGB").copy()
    draw = ImageDraw.Draw(img)
    for pred in pred_labels or []:
        text = f"{pred.get('class_name', '?')} {pred.get('confidence', 0):.2f}"
        _rect(draw, pred["bbox"], color, 2, text)
    return img


def draw_comparison(
    image: Image.Image,
    pred_labels: list[dict],
    rtdetr_pred_labels: list[dict],
) -> Image.Image:
    """Ảnh gốc + box của cả 2 model, tô màu theo mức độ đồng thuận giữa chúng.

    Ghép YOLO <-> RT-DETR bằng IoU (tái dùng match_labels, coi YOLO như "gt"
    tạm thời bằng label_id sinh sẵn). Box khớp vị trí + cùng class -> xanh lá
    (oke, 2 model đồng thuận). Box không khớp model kia (chỉ 1 model thấy)
    hoặc khớp vị trí nhưng khác class -> đỏ (nghi ngờ, cần soi lại).
    """
    img = image.convert("RGB").copy()
    draw = ImageDraw.Draw(img)

    yolo_with_ids = [{**p, "label_id": f"yolo_{i}"} for i, p in enumerate(pred_labels or [])]
    cmp = match_labels(yolo_with_ids, rtdetr_pred_labels or [])
    yolo_agrees: dict[int, bool] = {}
    rtdetr_agrees: dict[int, bool] = {}
    for m in cmp["matches"]:
        yolo_idx = int(m["gt_id"].split("_")[1])
        yolo_agrees[yolo_idx] = m["class_match"]
        rtdetr_agrees[m["pred_index"]] = m["class_match"]

    for i, pred in enumerate(pred_labels or []):
        color = "lime" if yolo_agrees.get(i) else "red"
        text = f"YOLO:{pred.get('class_name', '?')} {pred.get('confidence', 0):.2f}"
        _rect(draw, pred["bbox"], color, 2, text)
    for j, pred in enumerate(rtdetr_pred_labels or []):
        color = "lime" if rtdetr_agrees.get(j) else "red"
        text = f"RT-DETR:{pred.get('class_name', '?')} {pred.get('confidence', 0):.2f}"
        _rect(draw, pred["bbox"], color, 2, text)
    return img


def _issue_boxes(issue: dict, gt_by_id: dict, pred_by_index: dict) -> list[dict]:
    """Suy ra bbox liên quan tới issue từ evidence (mỗi issue_type có cấu trúc evidence khác nhau)."""
    ev = issue.get("evidence") or {}
    issue_type = issue.get("issue_type")
    boxes: list[dict] = []
    if issue_type == "wrong_class":
        gt = gt_by_id.get(ev.get("gt_id"))
        if gt:
            boxes.append(gt["bbox"])
        pred = pred_by_index.get(ev.get("pred_index"))
        if pred:
            boxes.append(pred["bbox"])
    elif issue_type == "duplicate_label":
        for key in ("label_a", "label_b"):
            gt = gt_by_id.get(ev.get(key))
            if gt:
                boxes.append(gt["bbox"])
    elif "bbox" in ev:
        boxes.append(ev["bbox"])
    return boxes


def draw_flagged(image: Image.Image, issues: list[dict], gt_labels: list[dict], pred_labels: list[dict]) -> Image.Image:
    """Ảnh + chỉ các nhãn bị gắn cờ, màu theo severity (đỏ=high, cam=medium, vàng=low)."""
    img = image.convert("RGB").copy()
    draw = ImageDraw.Draw(img)
    gt_by_id = {gt.get("label_id"): gt for gt in gt_labels or []}
    pred_by_index = {i: p for i, p in enumerate(pred_labels or [])}
    for issue in issues or []:
        color = SEVERITY_COLOR.get(issue.get("severity"), "red")
        text = f"{issue.get('issue_type')} ({issue.get('severity')})"
        for bbox in _issue_boxes(issue, gt_by_id, pred_by_index):
            _rect(draw, bbox, color, 3, text)
    return img


def _ensemble_issue_boxes(issue: dict, gt_by_id: dict) -> list[dict]:
    """Suy ra bbox liên quan tới issue của flag_issues_ensemble (evidence lồng yolo/rtdetr,
    khác cấu trúc phẳng gt_id/pred_index của _issue_boxes/flag_issues)."""
    ev = issue.get("evidence") or {}
    boxes: list[dict] = []
    label_id = issue.get("label_id")
    if label_id is not None:
        gt = gt_by_id.get(label_id)
        if gt:
            boxes.append(gt["bbox"])
        return boxes
    for key in ("yolo", "rtdetr"):
        pred = ev.get(key)
        if pred:
            boxes.append(pred["bbox"])
    return boxes


def draw_ensemble_flagged(image: Image.Image, issues: list[dict], gt_labels: list[dict]) -> Image.Image:
    """Ảnh + issue từ flag_issues_ensemble (GT vs cả 2 model), màu theo severity."""
    img = image.convert("RGB").copy()
    draw = ImageDraw.Draw(img)
    gt_by_id = {gt.get("label_id"): gt for gt in gt_labels or []}
    for issue in issues or []:
        color = SEVERITY_COLOR.get(issue.get("severity"), "red")
        text = f"{issue.get('issue_type')} ({issue.get('severity')}/{issue.get('agreement')})"
        for bbox in _ensemble_issue_boxes(issue, gt_by_id):
            _rect(draw, bbox, color, 3, text)
    return img


def run_agent(
    image_path: str,
    label_path: str | None,
    enable_rtdetr: bool,
) -> dict:
    payload = {
        "image_path": image_path,
        "enable_rtdetr": enable_rtdetr,
    }
    if label_path:
        payload["label_path"] = label_path
    return asyncio.run(agent.ainvoke(payload))


st.title("🔍 Label QA Agent — kiểm tra luồng hoạt động")
st.caption(
    "Upload một ảnh đã gán nhãn (+ file nhãn gốc nếu có). Agent sẽ chạy YOLO (+ RT-DETR nếu bật), "
    "đối chiếu với nhãn gốc, gắn cờ nghi vấn và nhờ LLM giải thích."
)

with st.sidebar:
    st.header("Cấu hình hiện tại")
    settings = get_settings()
    st.write(f"**YOLO model:** `{settings.yolo_model_name}`")
    st.write(f"**YOLO conf threshold:** `{settings.yolo_confidence_threshold}`")
    st.write(f"**LLM model:** `{settings.model_name}`")
    st.write(f"**LLM provider:** `{settings.llm_provider}`")
    if not settings.openai_api_key and not settings.google_api_key:
        st.warning("Chưa cấu hình OPENAI_API_KEY hoặc GOOGLE_API_KEY trong .env — bước llm_explain sẽ dùng fallback local.")

    st.divider()
    st.subheader("RT-DETR (POC)")
    st.write(f"**Model:** `{settings.rtdetr_model_name}`")
    st.write(f"**Conf threshold:** `{settings.rtdetr_confidence_threshold}`")
    enable_rtdetr = st.checkbox(
        "Bật RT-DETR cho lần chạy này",
        value=settings.enable_rtdetr,
        help="Detector transformer thay thế YOLO, chưa nối vào matching/flagging — chỉ để so sánh. Lần đầu chạy sẽ tự tải weights nếu chưa có.",
    )

col1, col2 = st.columns(2)
with col1:
    image_file = st.file_uploader("Ảnh (.jpg/.png)", type=["jpg", "jpeg", "png"])
with col2:
    label_file = st.file_uploader("File nhãn gốc — tuỳ chọn (.txt YOLO hoặc .xml VOC)", type=["txt", "xml"])

classes_file = None
if label_file is not None and label_file.name.endswith(".txt"):
    classes_file = st.file_uploader(
        "classes.txt — tuỳ chọn, cần nếu nhãn .txt dùng class_id thay vì tên class",
        type=["txt"],
        key="classes_file",
    )

run_clicked = st.button("▶️ Chạy agent", type="primary", disabled=image_file is None)

if run_clicked and image_file is not None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        image_path = tmp_path / image_file.name
        image_path.write_bytes(image_file.getvalue())

        label_path = None
        if label_file is not None:
            label_path = tmp_path / label_file.name
            label_path.write_bytes(label_file.getvalue())
            if classes_file is not None:
                (tmp_path / "classes.txt").write_bytes(classes_file.getvalue())

        extra_steps = []
        if enable_rtdetr:
            extra_steps.append("RT-DETR")
        spinner_msg = "Đang chạy agent (YOLO" + (" + " + " + ".join(extra_steps) if extra_steps else "") + " + matching + LLM explain)..."
        with st.spinner(spinner_msg):
            try:
                result = run_agent(
                    str(image_path),
                    str(label_path) if label_path else None,
                    enable_rtdetr,
                )
            except Exception as e:
                st.error(f"Agent raise exception ngoài dự kiến: {e}")
                st.stop()

        report = result.get("qa_report", {})
        status = report.get("status", "unknown")
        label, color = STATUS_STYLE.get(status, (status, "gray"))

        st.divider()
        st.subheader("Kết quả")
        st.markdown(f"### :{color}[{label}]")
        st.write(report.get("summary", ""))

        run_metadata = result.get("metadata") or {}
        yolo_latency = run_metadata.get("yolo_latency_ms") or {}
        if yolo_latency:
            st.caption(
                "YOLO latency: "
                f"wall={yolo_latency.get('inference_wall')} ms · "
                f"model_load={yolo_latency.get('model_load')} ms · "
                f"pre={yolo_latency.get('preprocess')} ms · "
                f"infer={yolo_latency.get('inference')} ms · "
                f"post={yolo_latency.get('postprocess')} ms"
            )
        if enable_rtdetr and run_metadata.get("rtdetr_error"):
            st.warning(f"RT-DETR lỗi, bỏ qua: {run_metadata['rtdetr_error']}")

        metrics = report.get("metrics") or {}
        if metrics:
            cols = st.columns(len(metrics))
            for c, (k, v) in zip(cols, metrics.items()):
                c.metric(k, f"{v:.3f}" if isinstance(v, float) else v)

        original = Image.open(image_path)
        gt_labels = result.get("gt_labels", [])
        pred_labels = result.get("pred_labels", [])
        rtdetr_pred_labels = result.get("rtdetr_pred_labels", [])
        issues = report.get("issues") or []

        st.markdown("**1. Ảnh gốc + GT** (xanh dương)")
        st.image(draw_gt(original, gt_labels), use_container_width=True)

        st.markdown(f"**2. Kết quả YOLO** (xanh lá, {len(pred_labels)} object)")
        st.image(draw_pred(original, pred_labels, color="lime"), use_container_width=True)

        st.markdown(f"**3. Kết quả RT-DETR** (cam, {len(rtdetr_pred_labels)} object)")
        if enable_rtdetr:
            st.image(draw_pred(original, rtdetr_pred_labels, color="orange"), use_container_width=True)
        else:
            st.info("RT-DETR đang tắt — bật checkbox ở sidebar để chạy.")

        st.markdown("**4. So sánh kết hợp YOLO + RT-DETR trên ảnh gốc**")
        if enable_rtdetr:
            st.image(
                draw_comparison(original, pred_labels, rtdetr_pred_labels),
                use_container_width=True,
            )
            st.caption("🟢 xanh = 2 model đồng thuận (khớp vị trí + cùng class) · 🔴 đỏ = nghi ngờ (chỉ 1 model thấy, hoặc khớp vị trí nhưng khác class).")
        else:
            st.info("RT-DETR đang tắt — bật checkbox ở sidebar để chạy.")

        st.markdown(f"**5. Nhãn bị gắn cờ — GT vs YOLO** ({len(issues)})")
        st.image(draw_flagged(original, issues, gt_labels, pred_labels), use_container_width=True)
        st.caption("🔴 high · 🟠 medium · 🟡 low (dùng cho qa_report chính thức)")

        st.markdown("**6. Nhãn bị gắn cờ — GT vs RT-DETR** (so sánh, không dùng cho qa_report)")
        if enable_rtdetr:
            rtdetr_match = match_labels(gt_labels, rtdetr_pred_labels)
            rtdetr_issues = flag_issues(
                rtdetr_match["matches"],
                rtdetr_match["unmatched_gt"],
                rtdetr_match["unmatched_pred"],
                gt_labels,
            )
            st.image(draw_flagged(original, rtdetr_issues, gt_labels, rtdetr_pred_labels), use_container_width=True)
            st.caption(f"🔴 high · 🟠 medium · 🟡 low ({len(rtdetr_issues)} issue, cùng rule flag_issues nhưng chạy trên GT vs RT-DETR — chỉ để so sánh)")
        else:
            st.info("RT-DETR đang tắt — bật checkbox ở sidebar để chạy.")

        st.markdown("**7. Nhãn bị gắn cờ — GT vs CẢ 2 model (bộ luật ensemble riêng)**")
        if enable_rtdetr:
            ensemble_issues = flag_issues_ensemble(gt_labels, pred_labels, rtdetr_pred_labels)
            st.image(draw_ensemble_flagged(original, ensemble_issues, gt_labels), use_container_width=True)
            st.caption(
                f"🔴 high (cả 2 model đồng thuận nghi vấn) · 🟠 medium (2 model bất đồng với nhau) · "
                f"🟡 low (chỉ 1 model phát hiện) — {len(ensemble_issues)} issue, bộ luật riêng "
                "(flag_issues_ensemble), độc lập với qa_report chính thức."
            )
            with st.expander(f"Chi tiết issue ensemble ({len(ensemble_issues)})"):
                if not ensemble_issues:
                    st.info("Không có issue nào được gắn cờ.")
                for issue in ensemble_issues:
                    sev = SEVERITY_STYLE.get(issue.get("severity"), issue.get("severity"))
                    st.markdown(
                        f"{sev} — **{issue.get('issue_type')}** "
                        f"({issue.get('label_id') or 'no id'}, agreement={issue.get('agreement')})"
                    )
                    st.json(issue.get("evidence") or {})
        else:
            st.info("RT-DETR đang tắt — bật checkbox ở sidebar để chạy.")

        st.markdown(f"**Chi tiết issues ({len(issues)})**")
        if not issues:
            st.info("Không có issue nào được gắn cờ.")
        for issue in issues:
            sev = SEVERITY_STYLE.get(issue.get("severity"), issue.get("severity"))
            with st.expander(f"{sev} — {issue.get('issue_type')} ({issue.get('label_id') or 'no id'})"):
                if issue.get("explanation"):
                    st.write(f"**Giải thích:** {issue['explanation']}")
                if issue.get("suggested_fix"):
                    st.write(f"**Đề xuất sửa:** {issue['suggested_fix']}")
                st.json(issue.get("evidence") or {})

        with st.expander("Raw qa_report (JSON)"):
            st.json(report)
        with st.expander("Raw agent state (debug: gt_labels/pred_labels/rtdetr_pred_labels/matches...)"):
            debug_state = {k: v for k, v in result.items() if k != "qa_report"}
            st.json(debug_state)
elif image_file is None:
    st.info("Upload ảnh để bắt đầu. Nếu không có file nhãn gốc, agent sẽ tự tìm theo quy ước dataset (images/↔labels/) — thường sẽ không tìm thấy với ảnh upload rời, nên nên đính kèm file nhãn.")
