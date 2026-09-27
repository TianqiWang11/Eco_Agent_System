# 预测结果与 UE 建模

状态：预测、建模、回执和聚焦链路已打通。2026-09-21 已把数据库可预测且与
UE Actor Label 精确对应的 1,383 个单木编号写入运行时 Actor Tags，缺失为 0；
TreeSimulation 与 PredictionSceneBridge 已进入新的 UE 5.4 发行包。默认启动脚本
现在优先使用：
`D:/TQ_Projects/UE_data/packages/CheBaLingPlatform_prediction_tagged_20260921/Windows/CheBaLingPlatform.exe`。

## 数据链路

1. Agent 的 `predict` 工具在 `predict_species_trees` 模式下，以用户输入树种
   和指定年份精确查询 PostgreSQL 中该树种全部可预测的单木；未指定年份时先询问。
2. 返回原模板 Excel，同时返回每棵树的编号、树种、年份、预测 DBH、估算树高、
   南北/东西冠径和冠体积。前端以逐棵数据通道消息发送，不让 UE 解析 Excel。
3. Pixel Streaming 播放器将预测指令送往 `chebaling.prediction` 通道。
   `PredictionSceneBridge` 仅用明确的 Actor Tag 或精确 Actor 名称匹配编号；
   不使用未经坐标配准的数据库 X/Y。找不到目标时返回错误，不生成替代树。
4. UE 以 `TreeSimulation` 的 `FTreeParams` 更新参数树，隐藏原 Actor，并返回
   逐棵回执。聊天列表只有收到成功回执才可点击；点击会聚焦到参数树。
   第一棵成功建模的树会自动聚焦。

DBH 和高度/冠径沿用预测工具的米单位；插件的 `FTreeParams` 也是米单位。
位置直接沿用 UE 中已匹配 Actor 的实际位置，因此不需要数据库坐标转换。
这些预测是实验性外推，不是实测值。只有在 UE 场景中已按编号建立 Tag/Actor
名称的树，才能被模型替换和聚焦。

## 可复现源码

- `infrastructure/ue-connection/plugins/TreeSimulation/` 从用户的
  `D:/TQ_Projects/UE_data/3Dmodel_control/Plugins/TreeSimulation/`
  移植，去掉了平台运行时自动弹出的示例参数面板。
- `infrastructure/ue-connection/plugins/PredictionSceneBridge/` 是新建的
  Pixel Streaming → 参数树插件桥。
- `infrastructure/ue-connection/player/uiless.ts` 是已部署播放器协议源码。
  构建时应输出到专用临时目录，**不能**直接运行原 webpack 配置写入
  `SignallingWebServer/Public`，因为它的 `output.clean=true` 会清理整个目录。

## UE 5.4 打包与验收状态

参数树原工程 `US_Tree` 来自 UE 5.8；源码兼容问题已修复并通过 UE 5.4 编译。
LCC4Unreal 的关键不是重新编译厂商闭源模块，而是按 XGRIDS 的预编译插件说明，
把 `Intermediate/Build/Win64/UnrealGame` 放入工程目标目录
`Intermediate/Build/Win64/CheBaLingPlatform`，并把插件的 x64 中间产物合并到工程
`Intermediate/Build/Win64/x64`。完成后 Development 游戏目标和完整 Cook 均通过，
无需下载另一份 LCC 插件。

原工程的 `BP_GameState` 仍序列化了已禁用的 Tracer Interactive `HttpLibrary` 与
`JsonLibrary` 节点。它们不参与当前 Agent/预测链路，但会让 Cook 最终返回 6 个旧结构错误。
打包脚本因此提供显式 `-IgnoreLegacyCookErrors` 兼容开关；默认构建不会隐藏错误。
若要恢复旧天气/HTTP 蓝图功能，应从原工程方取得适用于 UE 5.4、Win64 Development
和 Shipping 的完整 `HttpLibrary`、`JsonLibrary` 插件及购买授权，随后重新保存
`BP_GameState`，不应拿别的 HTTP/JSON 插件替代，因为序列化类型和模块名必须一致。

已验证：新包 13.84 GiB、17,198 个资源包；8000/8080/8888 监听；
`DefaultStreamer` 注册；UE 日志挂载 AgentSceneControl、LCC4Unreal、
PredictionSceneBridge、TreeSimulation，并连接 `ws://127.0.0.1:8888`。UE 5.4
运行时创建的 Pixel Streaming 输入组件存在地图切换和线程分发问题，桥接插件现会在
Pixel Streaming `OnReady` 后注册原生 UIInteraction 处理器，将消息切回游戏线程，
并在地图切换销毁接收器时自动恢复。

自动化实机验收使用编号 `0101046`：网页收到 `apply_prediction` 成功回执
“已更新 0101046 的 2030 年预测模型”，随后收到 `focus_prediction` 成功回执
“已聚焦预测树木”。测试脚本为 `tests/ue-prediction-live-smoke.cjs`；测试结束后已
重启 UE，未保留临时预测状态。标签迁移白名单与审计分别保存在
`data/processed/ue_scene_database_matched_ids.json`、
`data/processed/ue_scene_actor_inventory_after_tags.json`，修改前完整备份位于
`D:/TQ_Projects/UE_data/backups/actor-tags-before-20260921`。

仍建议正式交付时人工目视验收原模型隐藏、参数树尺寸变化与镜头构图；自动化测试已
覆盖真实浏览器、WebRTC 数据通道、UE 建模执行回执和聚焦执行回执。
从 UE 5.8 复制的三份示例材质不能被 UE 5.4 读取；代码会回退到默认材质，因此不会
阻止运行，但正式展示前应在 UE 5.4 中重建树皮、树叶材质和叶簇纹理。
