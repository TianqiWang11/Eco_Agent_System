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
  session/                     Events、Task State、Checkpoints
  tools/local_tools/           本地 Python 工具与结构化注册入口
  tools/mcp.py                 MCP Tools / Resources
  tools/sandbox_tools.py       沙箱工具入口
  sandbox/                     Interface、Local、Docker、Workspace、Manager
  telemetry/                   安全事件投影、OTLP 导出
  runtime.py                   模块装配、单进程任务调度
  api.py                       Session API / SSE
src/platform/data/             数据中心 API、PostgreSQL 连接和数据源状态
src/project_paths.py           根 data 目录的统一路径定义
data/                         全部项目数据、知识资料和预测输出
infrastructure/ue-connection/ UE / Pixel Streaming 连接与运维脚本
```

不再保留旧工作流、意图路由、自然语言参数解析器、流水线和回答合成器，也没有兼容编排模式。模型通过结构化工具参数执行任务；工具内部不再调用模型生成回答。

当前工具入口包括 `get_data`、`analysis`、`knowledge`、`database`、`predict`、`web_search` 和需审批的 `ue_scene`。Get_data 统一封装原始表读取脚本；Predict 使用已训练的树种感知胸径生长模型，并自动生成代码中定义的 Excel 输出模板。web_search 通过受控的 Exa MCP 查询公开互联网，无需逐次审批；其他通用 MCP 操作仍需审批。原绘图库保留的其他组合图、跨年比较等尚未全部注册，不能将保留函数视为已开放能力。

## 运行与测试

在仓库根目录使用项目 Python 虚拟环境，安装 `requirements.txt`。复制 `.env.example` 为 `.env` 并填写 `MOONSHOT_API_KEY`，不要提交密钥。模型入口固定为 Moonshot 官方 Kimi API，默认使用 `kimi-k3`，不提供其他模型 Provider。

```powershell
.venv/Scripts/python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --workers 1
.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider
```

此版本是模块化单机运行时，不是已部署的分布式系统。一个状态目录只允许一个服务进程。Session SQLite 只保存 Agent 任务状态；生态业务查询使用 `DATABASE_URL` 指向的 PostgreSQL，根 `data/reference` 中的 Excel 由 Get_data 支持旧数据读取与统计。旧合约任务保留历史但不能续跑，更新后请新建任务。

MCP 默认配置 Exa 的匿名限流搜索服务；Docker 默认禁用，不会回退到宿主机执行模型生成代码。测试不调用付费模型；生产模型、带密钥的 MCP、Docker 和 UE 端到端效果需要部署验收。

详见 [架构、接口与安全边界](agent-architecture.md)。
