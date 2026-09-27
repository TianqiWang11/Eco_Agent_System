# 本地演示

确保根目录 `.venv`、`.env`、本机 PostgreSQL 和 `D:\TQ_Projects\UE_data` 已准备好，然后双击根目录 `启动平台.bat`。门户地址为 `http://127.0.0.1:8000`；`停止平台.bat` 停止平台服务。

只启动 FastAPI 后端时可以双击根目录 `start_platform.bat`。它不会启动 UE 或 Pixel Streaming。UE 窗口由 `infrastructure/ue-connection` 中的脚本连接；局域网展示需另行检查本机防火墙和端口配置。

建议演示：先查看数据中心的 PostgreSQL 查询，再让 Agent 查询样地单木或做统计、绘图；未来年份预测会返回符合代码模板的 Excel 附件。预测结果属于实验性外推，不应当作实测值。所有密钥和数据库连接字符串仅留在服务器 `.env`，不进入前端。
