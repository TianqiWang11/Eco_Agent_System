# 车八岭生态数字孪生与 AI 智能分析平台

本仓库统一管理 Agent、平台服务、UE 连接和项目数据。生态业务库是本机 PostgreSQL，通过 `.env` 的 `DATABASE_URL` 连接；UE 工程与打包产物放在独立本地目录中。

## 目录结构

- `src/agent/`：Harness、Session、Tools/MCP、Sandbox 和 Telemetry。
- `src/platform/`、`frontend/`：FastAPI 平台接口与 Web 门户。
- `infrastructure/ue-connection/`：平台启动、停止、UE 重启、诊断、Pixel Streaming 和打包脚本。
- `data/reference/source_data/`：未经统一入库的原始业务表格和 GIS 数据。
- `data/reference/source_documents/`：RAG 的原始 PDF、Word 和 PPT 资料。
- `data/knowledge/`：经过提取、清洗的知识文本。
- `data/database_origin_table/`、`data/processed/`：数据库导入来源与预测输出。

预测结果驱动 UE 参数树的实现与当前打包限制见
[`docs/prediction-ue-integration.md`](docs/prediction-ue-integration.md)。
- `config/`、`storage/`：MCP 配置示例与 Agent 本地持久状态。
- `artifacts/packages/`：UE 打包产物的占位说明，实际产物不进入 Git。
- `启动平台.bat`、`停止平台.bat`：Windows 一键启停入口。

服务模块、工具和测试说明见 [服务说明](docs/service.md)。

## UE 本地数据

UE 相关大型文件统一存放在 `D:\TQ_Projects\UE_data`：

- `CheBaLingPlatform/`：UE 5.4 工程源文件、插件和缓存。
- `packages/`：Development、Debug、Staged 和正式打包产物。
- `PixelStreamingInfrastructure-UE5.4/`：官方 Pixel Streaming 运行环境。
- `material-backups/`：材质修复备份。

脚本默认使用上述目录。如需换盘或换路径，设置环境变量 `CHEBALING_UE_DATA_ROOT` 即可，无需修改项目代码。

## 本地启动

1. 确保 `D:\TQ_Projects\UE_data` 中的 UE 文件完整，并已准备根目录 `.venv`、`.env` 与 PostgreSQL。
2. 双击 `启动平台.bat`，访问 `http://127.0.0.1:8000`。
3. 使用 `停止平台.bat` 停止本项目启动的服务。

## Git 约定

- AI、Web、后端、编排脚本和数据接口共用当前这一个 Git 仓库。
- UE 工程、打包产物、缓存、Python/Node 环境、运行日志、密钥和临时文件不提交。
- 图片、Office/PDF、GIS 等必要的二进制参考资料使用 Git LFS。
- `.env.example` 可以提交，真实 `.env` 只保存在本机。
