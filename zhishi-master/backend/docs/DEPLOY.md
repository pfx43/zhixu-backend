# KT 后端部署指南

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
cd kt_backend
pip install -r requirements.txt
```

`requirements.txt` 内容：
```
torch>=1.12.0
numpy>=1.21.0
scikit-learn>=1.0.0
tqdm>=4.60.0
pandas>=1.3.0
openai>=1.0.0
fastapi>=0.100.0
uvicorn>=0.20.0
```

### 3. 生成先修矩阵

使用内置 7 技能数学示例：
```bash
python generate_matrix.py
```

或从 CSV 导入自定义学科数据：
```bash
# 先导出模板
python generate_matrix.py --template > my_skills.csv

# 编辑 my_skills.csv（用 Excel 或文本编辑器）
# 格式: 先修技能,后续技能

# 生成矩阵
python generate_matrix.py --csv my_skills.csv -o logic_matrix.npy
```

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
# 预期: {"status":"ok","skills_count":7,"model_loaded":true}
```

浏览器打开 `http://127.0.0.1:8765/docs` 查看交互式 API 文档。

---

## 二、配置说明

### 技能名称映射

编辑 `server.py` 中的 `SKILL_NAMES` 字典：

```python
SKILL_NAMES = {
    0: "加法",
    1: "减法",
    # ... 与 logic_matrix.npy 索引一一对应
}
```

### LADL 参数（lekt_service.py）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `epsilon` | 0.05 | 容忍裕度，允许微小违反 |
| `lambda_logic` | 0.1 | 正则化强度（训练用） |
| `beta` | 1.0 | LADL 修正强度 |

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
