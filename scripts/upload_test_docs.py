#!/usr/bin/env python3
"""批量上传 IWMS 测试文档到指定 KB。

用法:
  python3 scripts/upload_test_docs.py
"""

import os
import sys
import requests

BASE = "http://localhost:8080/api"
DOC_DIR = "scripts/test_docs/iwms/output"

# ---- 认证信息 ----
REFRESH_TOKEN = os.environ.get("REFRESH_TOKEN", "")
if not REFRESH_TOKEN:
    print("❌ 请先设置环境变量 REFRESH_TOKEN", file=sys.stderr)
    print("   export REFRESH_TOKEN=\"your-refresh-token\"", file=sys.stderr)
    sys.exit(1)
SPACE_ID = os.environ.get("SPACE_ID", "ec5f4dea-2fb2-42a3-8dfb-052c28eb36f5")

# ---- KB 映射 ----
KB_MAP = {
    "项目管理":   "41d3c741-cc0a-401e-8924-ff940caab397",
    "技术设计":   "b729e77f-0e60-4d49-b895-eeabf6472233",
    "质量测试":   "211800ed-1a8b-44a0-a748-7d7d138fbfbe",
    "市场与选型": "82b48f82-4bac-4d14-9327-3ecb84abcee0",
}

# ---- 文档 → KB 分配 ----
DOC_ASSIGNMENTS = [
    # (文件名, KB名, 版本)
    ("01_项目立项书.docx",          "项目管理",   "1.0"),
    ("02_需求规格说明书.docx",      "项目管理",   "1.0"),
    ("07_项目排期甘特表.xlsx",      "项目管理",   "1.0"),
    ("08_团队人员与分工表.xlsx",    "项目管理",   "1.0"),
    ("09_项目月度预算明细.xlsx",    "项目管理",   "1.0"),
    ("10_6月项目周会纪要.md",       "项目管理",   "1.0"),
    ("11_7月项目周会纪要.md",       "项目管理",   "1.0"),
    ("15_项目差旅报销制度.pdf",     "项目管理",   "1.0"),
    ("20_项目复盘总结.docx",        "项目管理",   "1.0"),

    ("03_系统架构设计文档.md",      "技术设计",   "1.0"),
    ("04_数据库ER图说明.md",        "技术设计",   "1.0"),
    ("05_REST_API接口规范.html",    "技术设计",   "1.0"),
    ("06_前端组件设计规范.md",      "技术设计",   "1.0"),
    ("13_权限模块设计文档.docx",    "技术设计",   "1.0"),
    ("14_部署运维手册.md",          "技术设计",   "1.0"),
    ("18_数据迁移方案.txt",         "技术设计",   "1.0"),

    ("12_Q2测试报告.pdf",           "质量测试",   "1.0"),
    ("17_用户验收测试用例.xlsx",    "质量测试",   "1.0"),

    ("16_竞品分析报告.pdf",         "市场与选型", "1.0"),
    ("19_第三方服务选型对比.md",    "市场与选型", "1.0"),
]


def get_context_token(refresh_token: str, space_id: str) -> str:
    """用 refresh token 切换到目标 Space，获取 context token。"""
    resp = requests.post(
        f"{BASE}/auth/switch-space",
        json={"space_id": space_id},
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    resp.raise_for_status()
    body = resp.json()
    if body["code"] != 0:
        raise RuntimeError(f"switch-space 失败: {body['message']}")
    return body["data"]["access_token"]


def upload_doc(ctx_token: str, filepath: str, kb_id: str, version: str) -> dict:
    """上传单个文档。"""
    filename = os.path.basename(filepath)
    ext = filename.rsplit(".", 1)[-1].lower()

    # MIME 类型映射（让后端识别文件类型）
    mime_map = {
        "pdf":  "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "md":   "text/markdown",
        "html": "text/html",
        "txt":  "text/plain",
    }
    mime = mime_map.get(ext, "application/octet-stream")

    with open(filepath, "rb") as f:
        resp = requests.post(
            f"{BASE}/documents",
            files={"file": (filename, f, mime)},
            data={
                "kb_id": kb_id,
                "effective_date": "2026-06-16",
                "version": version,
                # expiry_date 留空 = 长期有效
            },
            headers={"Authorization": f"Bearer {ctx_token}"},
        )
    resp.raise_for_status()
    body = resp.json()
    if body["code"] != 0:
        raise RuntimeError(f"上传失败: {body['message']}")
    return body["data"]


# ============================================================
# 主流程
# ============================================================

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    print("=== 1. 获取 context token ===")
    ctx_token = get_context_token(REFRESH_TOKEN, SPACE_ID)
    print(f"   token: {ctx_token[:50]}...")

    print(f"\n=== 2. 批量上传 {len(DOC_ASSIGNMENTS)} 个文档 ===\n")
    success = 0
    failed = []

    for filename, kb_name, version in DOC_ASSIGNMENTS:
        filepath = os.path.join(DOC_DIR, filename)
        kb_id = KB_MAP[kb_name]

        if not os.path.exists(filepath):
            print(f"   ✗ {filename} → 文件不存在: {filepath}")
            failed.append(filename)
            continue

        try:
            result = upload_doc(ctx_token, filepath, kb_id, version)
            doc_id = result.get("id", "?")
            name = result.get("file_name", filename)
            print(f"   ✓ [{kb_name}] {name}  (id={doc_id[:8]}...)")
            success += 1
        except Exception as e:
            print(f"   ✗ [{kb_name}] {filename}  {e}")
            failed.append(filename)

    print(f"\n=== 完成: 成功 {success}/{len(DOC_ASSIGNMENTS)} ===")
    if failed:
        print(f"失败: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
