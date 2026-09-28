# Chebaling Agent

车八岭生态数据问答、统计和可视化平台。Agent 只使用新架构；原本地 Python 计算与绘图代码位于 `src/agent/tools/local_tools/`。

## 结构

```text
app.py                         FastAPI / App Server
frontend/platform.html         平台页面
frontend/agent.js              Session、审批与执行事件
src/agent/
  contracts.py                 Model / Agent / Tool 合约
  harness/                     Loop、Context Manager、Model Client、Dispatcher、Policy
  environment/                 PostgreSQL 隐藏业务数据表导入与访问
  session/                     Events、Task State、Checkpoints
  tools/local_tools/           本地 Python 工具与结构化注册入口
  tools/mcp.py                 MCP Tools / Resources
  sandbox/                     预留的隔离实现（当前 Runtime 不装载）
  telemetry/                   安全事件投影、OTLP 导出
  runtime.py                   模块装配、单进程任务调度
  api.py                       Session API / SSE
src/platform/data/             数据中心 API、PostgreSQL 连接和数据源状态
src/project_paths.py           根 data 目录的统一路径定义
data/                         全部项目数据、知识资料和预测输出
infrastructure/ue-connection/ UE / Pixel Streaming 连接与运维脚本
```

不再保留旧工作流、意图路由、自然语言参数解析器、流水线和回答合成器，也没有兼容编排模式。模型通过结构化工具参数执行任务；工具内部不再调用模型生成回答。

当前工具入口包括 `get_data`、`analysis`、`knowledge`、`database`、`predict`、`web_search` 和需审批的 `ue_scene`。Get_data 与 analysis 从 PostgreSQL 的 `public.forest_inventory`（完整调查记录）和 `public.tree_segmentation`（完整单木分割记录）读取；knowledge 使用独立的 LlamaIndex + Chroma 持久化向量库。Predict 使用已训练的树种感知胸径生长模型，并自动生成代码中定义的 Excel 输出模板。web_search 通过受控 MCP 查询公开互联网，无需逐次审批；其他通用 MCP 操作仍需审批。

## 运行与测试

在仓库根目录使用项目 Python 虚拟环境，安装 `requirements.txt`。复制 `.env.example` 为 `.env` 并填写 `MOONSHOT_API_KEY`，不要提交密钥。模型入口固定为 Moonshot 官方 Kimi API，默认使用 `kimi-k3`，不提供其他模型 Provider。

```powershell
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
.venv/Scripts/python.exe -m src.agent.environment.bootstrap
.venv/Scripts/python.exe -m src.agent.tools.local_tools.knowledge.index_builder
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
```

数据库管理员首次执行 `database/prepare_agent_schema.sql`，之后应用账号即可在 `public` 中幂等导入两张完整业务表。数据中心仍由固定 API 决定展示范围。Chroma 数据存储在 `storage/chroma`，与 PostgreSQL 分离。

此版本是模块化单机运行时，不是已部署的分布式系统。一个状态目录只允许一个服务进程。Session SQLite 只保存 Agent 任务状态；生态业务表使用 `DATABASE_URL` 指向的 PostgreSQL，RAG 使用独立 Chroma。数据中心 API 仍只暴露编号已对应的 `trees` 与 `tree_measurements`。旧合约任务保留历史但不能续跑，更新后请新建任务。

MCP 默认配置 Exa 的匿名限流搜索服务；Sandbox 当前不注册到 Runtime，也不会回退到宿主机执行模型生成代码。生产模型、带密钥的 MCP 和 UE 端到端效果需要部署验收。

详见 [架构、接口与安全边界](agent-architecture.md)。
