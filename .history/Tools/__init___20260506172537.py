from langchain_core.tools import tool


@tool
def output_formatter(answer: str, source: str = "", confidence: float = 1.0) -> dict:
    """将最终答案格式化为 JSON 格式输出。每次回答用户问题时必须调用此工具。

    Args:
        answer: 回答用户问题的最终答案
        source: 答案的来源或依据（可选）
        confidence: 对答案的置信度，0-1之间（可选）
    """
    return {
        "answer": answer,
        "source": source,
        "confidence": confidence,
    }
