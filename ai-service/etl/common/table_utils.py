"""表格渲染工具 — 二维数组 → Markdown Table 文本。"""


def rows_to_markdown(rows: list[list[str]]) -> str:
    """将二维数组渲染为 Markdown Table 文本。

    统一 docx 和 xlsx 解析器中的重复实现。
    第一行作为表头，自动补齐不等长的列。
    """
    if not rows:
        return ""

    max_cols = max(len(r) for r in rows)
    lines = []

    # 表头
    header = rows[0] + [""] * (max_cols - len(rows[0]))
    lines.append("| " + " | ".join(header[:max_cols]) + " |")
    # 分隔线
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    # 数据行
    for row in rows[1:]:
        padded = row + [""] * (max_cols - len(row))
        lines.append("| " + " | ".join(padded[:max_cols]) + " |")

    return "\n".join(lines)
