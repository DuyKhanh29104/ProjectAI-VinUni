from langgraph.graph import END, StateGraph

from src.agents.nodes.flagging import flag_issues_node
from src.agents.nodes.llm_explain import llm_explain_node
from src.agents.nodes.load_gt_labels import load_gt_labels_node
from src.agents.nodes.matching import match_labels_node
from src.agents.nodes.metrics import compute_metrics_node
from src.agents.nodes.report import build_report_node
from src.agents.nodes.validate_input import validate_input_node
from src.agents.nodes.yolo_inference import run_yolo_inference_node
from src.agents.state import LabelQAState


def route_after_load_gt(state: LabelQAState) -> str:
    """Dừng sớm nếu không parse được file nhãn gốc."""
    return "build_report" if state.get("error") else "run_yolo_inference"


def route_after_yolo(state: LabelQAState) -> str:
    """Dừng sớm nếu YOLO inference lỗi."""
    return "build_report" if state.get("error") else "validate_input"


def route_after_validation(state: LabelQAState) -> str:
    """Bỏ qua toàn bộ pipeline nếu input không hợp lệ."""
    return "build_report" if state.get("error") else "match_labels"


def route_after_flagging(state: LabelQAState) -> str:
    """Chỉ gọi LLM khi có issue cần giải thích, tiết kiệm token cho case PASS."""
    return "llm_explain" if state.get("flagged_issues") else "build_report"


def build_graph() -> StateGraph:
    graph = StateGraph(LabelQAState)

    # Nodes
    graph.add_node("load_gt_labels", load_gt_labels_node)
    graph.add_node("run_yolo_inference", run_yolo_inference_node)
    graph.add_node("validate_input", validate_input_node)
    graph.add_node("match_labels", match_labels_node)
    graph.add_node("compute_metrics", compute_metrics_node)
    graph.add_node("flag_issues", flag_issues_node)
    graph.add_node("llm_explain", llm_explain_node)
    graph.add_node("build_report", build_report_node)

    # Edges
    graph.set_entry_point("load_gt_labels")
    graph.add_conditional_edges("load_gt_labels", route_after_load_gt)
    graph.add_conditional_edges("run_yolo_inference", route_after_yolo)
    graph.add_conditional_edges("validate_input", route_after_validation)
    graph.add_edge("match_labels", "compute_metrics")
    graph.add_edge("compute_metrics", "flag_issues")
    graph.add_conditional_edges("flag_issues", route_after_flagging)
    graph.add_edge("llm_explain", "build_report")
    graph.add_edge("build_report", END)

    return graph.compile()


agent = build_graph()
