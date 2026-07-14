"""ONNX 模型下载与管理 — Phase 1b-full。

模型来源: HuggingFace InfiniFlow/deepdoc
repo: https://huggingface.co/InfiniFlow/deepdoc

模型文件:
    - ocr/det.onnx        — DBNet 文本检测 (~10MB)
    - ocr/rec.onnx        — CRNN 文本识别 (~15MB)
    - ocr/ocr.res         — 字符字典
    - layout.onnx         — YOLOv10 布局识别 (~5MB)
    - table.onnx          — 表格结构识别 (~15MB)

总计约 50MB（模型本身，不含 ONNX Runtime）。
"""

import os
from pathlib import Path

MODEL_DIR = Path(__file__).parent.parent.parent.parent / "models" / "deepdoc"
REPO_ID = "InfiniFlow/deepdoc"
# 国内默认使用 hf-mirror.com 镜像，可通过 HF_ENDPOINT 覆盖
_HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")
_download_attempted = False  # 全局：下载只尝试一次


def get_model_dir() -> Path:
    """返回模型存储目录（自动创建）。"""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return MODEL_DIR


def ensure_models() -> bool:
    """确保所有 ONNX 模型已下载。

    首次调用时自动从 HuggingFace 下载，约 50MB。
    后续调用直接返回 True。

    Returns:
        True 如果所有模型就绪，False 如果下载失败
    """
    global _download_attempted

    d = get_model_dir()

    required = [
        d / "det.onnx",     # 文本检测 (DBNet)
        d / "rec.onnx",     # 文本识别 (CRNN)
        d / "ocr.res",      # 字符字典
    ]

    # 检查所有必需文件
    missing_required = [f for f in required if not f.exists()]
    if not missing_required:
        return True

    # 已经尝试过下载，不再重试
    if _download_attempted:
        return False
    _download_attempted = True

    # 快速检查镜像连通性
    import socket
    from urllib.parse import urlparse
    host = urlparse(_HF_ENDPOINT).hostname or "hf-mirror.com"
    try:
        socket.create_connection((host, 443), timeout=5)
    except OSError:
        print(f"⚠️ {host} 不可达，跳过模型下载。手动下载:")
        print(f"   HF_ENDPOINT={_HF_ENDPOINT} huggingface-cli download {REPO_ID} --local-dir {d}")
        return False

    # 尝试从镜像下载
    try:
        os.environ.setdefault("HF_ENDPOINT", _HF_ENDPOINT)
        from huggingface_hub import snapshot_download
        snapshot_download(
            repo_id=REPO_ID,
            local_dir=str(d),
            local_dir_use_symlinks=False,
            resume_download=True,
            endpoint=_HF_ENDPOINT,
        )
        print(f"✅ 模型下载完成: {d}")
        return True
    except ImportError:
        print("huggingface_hub 未安装，无法自动下载模型")
        return False
    except Exception as e:
        print(f"模型下载失败: {e}")
        print(f"请手动下载: https://huggingface.co/{REPO_ID}")
        print(f"放置到: {d}")
        return False


def get_model_path(name: str) -> str | None:
    """获取指定模型文件的路径。

    Args:
        name: 模型文件名，如 "ocr/det.onnx", "layout.onnx"

    Returns:
        文件路径或 None
    """
    path = get_model_dir() / name
    if path.exists():
        return str(path)
    return None
