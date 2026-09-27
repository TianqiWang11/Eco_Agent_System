# 项目数据

本地的 `reference/source_data/` 保存原始业务表格和 GIS 文件；
`reference/source_documents/` 保存知识库原始 PDF、Word 和 PPT 文档。
这些目录以及数据库导入表、论文解析文本均被 `.gitignore` 排除，不进入公开仓库。
目录使用英文名称，文件本身保留原始名称。

现有 PostgreSQL 业务库通过仓库根目录 `.env` 的 `DATABASE_URL` 连接；`processed/` 保留导入数据与预测输出。后续建议继续维护：

- 字段字典与数据来源说明；
- 脱敏的小型测试样本；
- 数据库表结构和 API 契约；
- 原始数据的版本、责任人和更新时间。

原始调查数据、论文、内部文档和包含敏感信息的生产数据不得提交到公开仓库。
