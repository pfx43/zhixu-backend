# KT 后端部署指南

## 应用后端部署（Windows 云服务器）

生产入口为项目根目录下的 `server.py:app`。更新代码后必须安装依赖、执行
迁移并重新启动进程，不能只确认旧进程仍占用 8765 端口。

```powershell
cd C:\zhixu-backend
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\alembic.exe upgrade head
.\start_server.ps1
```

`20260802_auth_sessions` 迁移会创建持久化会话表；
`20260802_note_revision` 会为既有 `user_notes` 增加非空 `revision` 并以 `1`
初始化历史行。若历史服务已通过 `create_all()` 创建相关表，迁移会接管并写入版本
记录，不会重复建表；必须在部署包含版本化 PATCH 的代码前执行 `alembic upgrade head`。
升级前已有内存 Token 无法恢复，用户需要登录一次；此后有效 Token 不会因服务重启丢失。

### 当前迁移链（v2.4）

```
20260802_note_revision
    ├── 20260804_question_fallbacks   (隔离历史固定占位题模板)
    └── 20260805_note_soft_delete     (笔记软删除：deleted_at / deleted_by_revision)
            └── 20260805_note_attachments  (笔记附件表 note_attachments)
```

`alembic upgrade head` 会自动应用所有 head。部署后可通过 `alembic current` 验证
所有 head 均已应用。

### ⚠️ 部署前注意

1. **迁移不可逆**：`20260804_question_fallbacks` 的 downgrade 为空（清理的引用数据
   无法无损恢复）。**生产环境执行前请先备份数据库**。
2. **存储目录**：笔记附件上传写入 `storage/notes/{user_id}/` 目录。确保服务器进程
   对项目根目录下的 `storage/` 有读写权限。
3. **Breaking Change**：`DELETE /api/v1/notes/{note_id}` 现在需要
   `{"expected_revision": N}` body。旧 Flutter 客户端直接调用将返回 422。
   详见 `docs/notes_前端对接文档.md`。

`start_server.ps1` 使用脚本所在目录解析路径，启动前拒绝复用已占用的 8765 端口。
启动校验默认等待 60 秒，可通过 `ZHISHI_STARTUP_TIMEOUT_SECONDS` 调整。只有
`/health` 返回 `api_contract.status=ok`，确认以下 4 个接口均已加载后才报告成功：

```text
/api/v1/onboarding/state
/api/v1/onboarding/step
/api/v1/onboarding/complete
/api/v1/onboarding/restart
```

若提示端口被旧进程占用，先确认并停止旧后端，再重新执行脚本。
端口默认是 8765；需要临时改端口时可设置 `ZHISHI_BACKEND_PORT`。

## 环境要求

| 项目 | 要求 |
|------|------|
| OS | Windows x86_64 |
| Python | **3.14**（必须，.pyd 只此版本） |
| Conda | 推荐，用于环境隔离 |
| 内存 | >= 2GB（PyTorch 占用） |

## 一、首次部署

### 1. 创建 Conda 环境

```bash
conda create -n xzs python=3.14 -y
conda activate xzs
```

### 2. 安装依赖

```bash
cd C:\zhixu-backend
pip install -r requirements.txt
```

### 3. 准备先修矩阵

先修矩阵 `logic_matrix.npy` 位于 `data/knowledge_graph/` 目录下。
如需重新生成，参见 `3rdParty/lekt_release_cython(3)/` 目录中的脚本。

### 4. 启动服务

```bash
# 方式 A：直接运行
uvicorn server:app --host 127.0.0.1 --port 8765

# 方式 B：双击 Windows 批处理
start_server.bat
```

### 5. 验证

```bash
curl http://127.0.0.1:8765/health
# 关键字段: {"api_contract":{"status":"ok","missing_paths":[]}}
```

浏览器打开 `http://127.0.0.1:8765/docs` 查看交互式 API 文档。

---

## 二、配置说明

### OCR 后端配置

OCR 后端通过 `.env` 文件中的 `OCR_BACKEND` 配置：

| 值 | 说明 |
|----|------|
| `local` | PaddleOCR 本地识别（默认，需安装 paddleocr） |
| `baidu` | 百度云 OCR API（需配置 `BAIDU_OCR_API_KEY` / `BAIDU_OCR_SECRET_KEY`） |
| `auto` | 优先 PaddleOCR，不可用时回退百度 OCR |

详见 `.env.example` 模板文件。

### 修改端口

```bash
uvicorn server:app --host 127.0.0.1 --port 自定义端口
```

Flutter 端配置：`设置页面 → KT 后端地址` 填入对应地址。

---

## 三、降级方案

如果 .pyd 文件不可用（如 Python 版本不对、系统不兼容），系统自动切换到**纯 NumPy 算法**：

| .pyd 模式 | NumPy 回退 |
|-----------|------------|
| LEKT 训练正则化 | 不可用（无损失回传） |
| LADL 推理修正 | ✅ 纯 NumPy 实现 |
| LVR/VS 评估 | ✅ 纯 NumPy 实现 |
| 学习路径推荐 | ✅ 纯 NumPy 实现 |

**回退模式限制**：
- 修正精度略低于 .pyd 优化版（约 80-90% 效果）
- 不支持 `logic_loss` 训练梯度
- 对 APP 集成无影响（APP 只用推理/评估/推荐接口）

---

## 四、故障排查

| 症状 | 原因 | 解决 |
|------|------|------|
| `ImportError: lekt_api` | Python 不是 3.14 | `python --version` 确认，切到 xzs 环境 |
| `logic_matrix.npy not found` | 矩阵未生成 | 运行 `python generate_matrix.py` |
| `Model not loaded` | .pyd 未找到 | 检查 4 个 .pyd 文件在同目录 |
| 端口被占用 | 8765 已被占用，或旧进程未释放 | 先执行 `netstat -ano | findstr :8765` 查找占用进程；若是旧服务，执行 `taskkill /PID <PID> /F` 结束；也可改用其他端口，如 `--port 8766` |
| `WinError 10048` | 同一个端口被重复绑定，通常是上次服务未正常退出 | 关闭占用进程后重试；若需保留旧进程，改用新的端口号 |
| 连接被拒绝 | 防火墙拦截或地址绑定问题 | 允许 Python 通过防火墙，或使用 `--host 0.0.0.0` 监听 |
| `torch` 安装失败 | 网络/平台问题 | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| `TCN 健康检查失败 / All connection attempts failed` | TCN 引擎服务未启动或地址错误 | 检查 `http://127.0.0.1:8001` 是否可访问；若 TCN 未部署，后端会自动降级，但部分 KT 能力不可用 |
| `401 Unauthorized` | 登录态失效或未携带有效 token | 先调用登录接口获取 token，并在后续请求头里带上 `Authorization: Bearer <token>` |
| `500 Internal Server Error` | 业务代码异常，常见于数据库或请求参数问题 | 查看后端控制台日志，重点看 `app.services.tcn_client`、数据库初始化和 SQLAlchemy 异常 |

---

## 五、生产环境建议

当前为本地单机部署。如需远程/多用户：

1. 改为 `--host 0.0.0.0`（监听所有接口）
2. 前面加 Nginx 反向代理
3. 加 API 认证（FastAPI middleware）
4. 用 `gunicorn + uvicorn workers` 多进程
5. 数据库持久化学习记录
