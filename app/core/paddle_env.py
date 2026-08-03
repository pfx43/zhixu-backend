"""PaddlePaddle CPU 兼容：在 import paddle 之前禁用 oneDNN/MKLDNN。"""
import os

_applied = False


def apply_paddle_cpu_compat_env() -> None:
    """避免 Paddle 3.x + oneDNN 触发 ConvertPirAttribute2RuntimeAttribute 等错误。"""
    global _applied
    if _applied:
        return
    os.environ["FLAGS_use_mkldnn"] = "0"
    os.environ["FLAGS_use_dnnl"] = "0"
    os.environ.setdefault("PADDLE_DISABLE_MKLDNN", "1")
    os.environ.setdefault("FLAGS_enable_mkldnn", "0")
    os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
    _applied = True


apply_paddle_cpu_compat_env()
