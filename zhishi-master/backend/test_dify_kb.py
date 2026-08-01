"""测试 DifyKB.create_dataset — 验证 Dify API 连通性"""
import sys
import os

# 确保能导入 app 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.dify_kb import DifyKB
from app.core.config import DIFY_BASE_URL, DIFY_DATASET_API_KEY
import uuid

print(f"DIFY_BASE_URL: {DIFY_BASE_URL}")
print(f"DIFY_API_KEY: {DIFY_DATASET_API_KEY[:20]}...")

try:
    kb_name = f"test_{uuid.uuid4().hex[:8]}"
    print(f"\n正在创建知识库: {kb_name} ...")
    dataset_id = DifyKB.create_dataset(kb_name, "测试用知识库")
    print(f"✅ 创建成功! dataset_id = {dataset_id}")
except Exception as e:
    print(f"❌ 创建失败: {type(e).__name__}: {e}")