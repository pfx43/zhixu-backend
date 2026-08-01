# 后端迁移计划：kt_backend → zhishi-master

> 目标：以 zhishi-master 为基座，迁移 kt_backend 的 Dify 配置后推送到新仓库 zhixu-backend

## 文件操作清单

| # | 操作 | 文件 | 说明 |
|:---:|:---:|------|------|
| 1 | 复制 | `kt_backend/.env` → `zhishi-master/backend/.env` | Dify Key + DB 密码 |
| 2 | 修改 | `zhishi-master/backend/.env` | 加 `RAG_BACKEND=dify` + 清空 tongyi |
| 3 | 验证 | `dify_kb.py` | 确认 tongyi fix 已应用（provider 为空时不传） |
| 4 | 修改 | `zhishi-master/backend/.gitignore` | 合并 kt_backend 的排除规则 |
| 5 | 更新 | `.env.example` | 更新为 zhishi-master 需要的完整模板 |
| 6 | 测试 | 启动后端 + 注册用户 | 验证 Dify 知识库创建 + Chat 返回 AI 回复 |
| 7 | 推送 | GitHub 创建 zhixu-backend | git init → add → commit → push |