"""生成测试文档脚本 — 使用项目配置的 LLM 生成企业风格文档，输出为多种格式。

用法:
    cd /home/zsl/projects/my_agent/ai-service
    uv run python ../scripts/generate_test_docs.py

输出:
    test_docs/ 目录下的文档文件
"""

import os
import sys
from pathlib import Path

# 将 ai-service 加入 sys.path，以便导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent / "ai-service"))

from core.config import load_settings
from llm.factory import ModelFactory


# ============================================================
# 文档清单 — 每份文档的元数据和 LLM 生成提示
# ============================================================
DOC_MANIFEST = [
    {
        "filename": "ACME公司差旅报销制度.pdf",
        "format": "pdf",
        "scope_type": "company",
        "scope_id": "acme-corp",
        "classification": "public",
        "system_prompt": (
            "你是一位有15年经验的企业行政总监，正在起草公司的正式管理制度文件。"
            "请生成一份完整的、正式的、可直接作为企业制度的文档。"
            "使用正式的公文语言，包含清晰的章节结构、条款编号。"
            "内容要具体、可操作，不要空泛的套话。"
            "加入一些看起来真实的数据（如金额、天数、城市名等）让文档更可信。"
            "回复只包含文档正文，不要包含任何解释性前缀或后缀。"
        ),
        "user_prompt": (
            "请生成一份《ACME科技有限公司差旅报销管理制度》的完整文档。\n\n"
            "文档应包含以下章节：\n"
            "1. 总则 — 制度目的、适用范围、基本原则\n"
            "2. 差旅标准 — 交通工具等级标准（飞机/高铁/火车）、住宿标准（一线城市800元/晚，"
            "二线城市500元/晚，其他350元/晚）、餐饮补贴（150元/天包干）\n"
            "3. 出差审批流程 — 普通员工需部门负责人审批，跨省出差需分管副总审批，"
            "单次预算超2万元需总经理审批\n"
            "4. 报销规范 — 报销时限（出差结束后7个工作日内提交）、发票要求（增值税专用发票）、"
            "报销单填写规范\n"
            "5. 违规处理 — 虚报费用按金额3倍罚款并记过，情节严重解除劳动合同\n"
            "6. 附则 — 制度解释权归行政部，自发布之日起执行\n\n"
            "要求：约3000字，语言正式规范，条款清晰可执行。"
        ),
    },
    # 更多文档在此添加...
]


def generate_content(settings, system_prompt: str, user_prompt: str) -> str:
    """使用配置的 LLM 生成文档内容。"""
    llm = ModelFactory.create_llm(settings.llm)

    print(f"  使用模型: {llm.get_model_name()}")
    response = llm.generate_content(
        prompt=user_prompt,
        context=[
            {"role": "system", "content": system_prompt},
        ],
    )
    content = response.content.strip()
    if response.usage:
        print(f"  Token 用量: prompt={response.usage.get('prompt_tokens', '?')}, "
              f"completion={response.usage.get('completion_tokens', '?')}")
    return content


def generate_pdf(content: str, output_path: Path) -> None:
    """将内容渲染为中文 PDF。"""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()

    # 注册中文 TrueType 字体
    font_path = _find_chinese_font()
    if font_path:
        pdf.add_font("CJK", "", font_path, uni=True)
        pdf.add_font("CJK", "B", font_path, uni=True)
        title_font = ("CJK", "B", 18)
        body_font = ("CJK", "", 11)
        heading_font = ("CJK", "B", 14)
    else:
        print("  [警告] 未找到中文字体，使用内置字体（中文将无法正常显示）")
        title_font = ("Helvetica", "B", 18)
        body_font = ("Helvetica", "", 11)
        heading_font = ("Helvetica", "B", 14)

    # 逐行处理内容
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            pdf.ln(4)
            continue

        # 判定行类型并设置样式
        if line.startswith("# ") or line.startswith("《"):
            # 一级标题 = 文档标题
            pdf.set_font(*title_font)
            pdf.multi_cell(0, 10, line.lstrip("# ").strip(), align="C")
            pdf.ln(6)
        elif line.startswith("## "):
            # 二级标题 = 章节标题
            pdf.set_font(*heading_font)
            pdf.ln(4)
            pdf.multi_cell(0, 8, line.lstrip("# ").strip())
            pdf.ln(2)
        elif line.startswith("### "):
            # 三级标题
            pdf.set_font(*heading_font)
            pdf.multi_cell(0, 8, line.lstrip("# ").strip())
            pdf.ln(1)
        elif line.startswith("- ") or line.startswith("* "):
            # 列表项
            pdf.set_font(*body_font)
            pdf.multi_cell(0, 6, f"    • {line[2:].strip()}")
        elif line[0].isdigit() and ("." in line[:3] or "、" in line[:3]):
            # 编号行
            pdf.set_font(*body_font)
            pdf.multi_cell(0, 6, line)
        else:
            # 普通段落
            pdf.set_font(*body_font)
            pdf.multi_cell(0, 6, line)

    pdf.output(str(output_path))
    print(f"  PDF 已生成: {output_path} ({output_path.stat().st_size} bytes)")


def _find_chinese_font() -> str | None:
    """查找系统中可用的中文字体。"""
    candidates = [
        # Windows (WSL)
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/arphic/ukai.ttc",
        # macOS/Linux
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        # 当前目录
        "simhei.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            print(f"  使用字体: {path}")
            return path
    return None


def main():
    output_dir = Path(__file__).parent / "test_docs"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("加载配置...")
    settings = load_settings()

    for i, doc in enumerate(DOC_MANIFEST, 1):
        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(DOC_MANIFEST)}] 生成: {doc['filename']}")
        print(f"  格式: {doc['format']} | Scope: {doc['scope_type']}/{doc['scope_id']} | 密级: {doc['classification']}")

        # 调用 LLM 生成内容
        print(f"  正在调用 LLM 生成内容...")
        content = generate_content(settings, doc["system_prompt"], doc["user_prompt"])
        print(f"  生成完成，共 {len(content)} 字符")

        # 保存原始文本（备份）
        txt_path = output_dir / f"{doc['filename'].rsplit('.', 1)[0]}.txt"
        txt_path.write_text(content, encoding="utf-8")

        # 根据格式输出
        if doc["format"] == "pdf":
            pdf_path = output_dir / doc["filename"]
            generate_pdf(content, pdf_path)
        else:
            output_path = output_dir / doc["filename"]
            output_path.write_text(content, encoding="utf-8")
            print(f"  文件已生成: {output_path}")

    print(f"\n{'=' * 60}")
    print(f"全部完成！文档输出目录: {output_dir.resolve()}")
    print(f"\n文件列表:")
    for f in sorted(output_dir.iterdir()):
        if f.is_file():
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
