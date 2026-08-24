import ast
import operator
from collections.abc import Callable
from typing import cast

from langchain_core.tools import tool

# Safe operator mapping for calculator
NumericOperator = Callable[..., float]

_SAFE_OPERATORS: dict[type[ast.AST], NumericOperator] = {
    ast.Add: cast(NumericOperator, operator.add),
    ast.Sub: cast(NumericOperator, operator.sub),
    ast.Mult: cast(NumericOperator, operator.mul),
    ast.Div: cast(NumericOperator, operator.truediv),
    ast.FloorDiv: cast(NumericOperator, operator.floordiv),
    ast.Mod: cast(NumericOperator, operator.mod),
    ast.Pow: cast(NumericOperator, operator.pow),
    ast.USub: cast(NumericOperator, operator.neg),
    ast.UAdd: cast(NumericOperator, operator.pos),
}


@tool
def search_knowledge(query: str) -> str:
    """Tìm kiếm thông tin trong knowledge base.

    Args:
        query: Câu hỏi cần tìm kiếm

    Returns:
        Kết quả tìm kiếm
    """
    # TODO: Implement actual search logic (e.g., RAG with vector store)
    return f"Kết quả tìm kiếm cho: {query}"


@tool
def calculate(expression: str) -> str:
    """Tính toán biểu thức toán học an toàn (không dùng eval).

    Hỗ trợ: +, -, *, /, //, %, ** và dấu ngoặc.

    Args:
        expression: Biểu thức cần tính (ví dụ: "2 + 3 * 4")

    Returns:
        Kết quả tính toán
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval_node(tree.body)
        return str(result)
    except (SyntaxError, ValueError, TypeError, ZeroDivisionError) as e:
        return f"Lỗi tính toán: {e}"


def _eval_node(node: ast.AST) -> float:
    """Recursively evaluate AST node using safe operators only."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value)}")
    elif isinstance(node, ast.UnaryOp):
        op_func = _SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_func(_eval_node(node.operand))
    elif isinstance(node, ast.BinOp):
        op_func = _SAFE_OPERATORS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op_func(_eval_node(node.left), _eval_node(node.right))
    else:
        raise ValueError(f"Unsupported expression: {type(node).__name__}")
