# 项目开发 Wiki

更新日期：2026-09-21。Wiki 保存在仓库的 `docs/wiki/`，随源代码提交和迁移；本文是统一导航，具体实现说明继续维护在原文档中。

项目当前采用 **Linux 制作视频训练数据与候选命令、Windows 运行游戏** 的分工。Linux 已完成20集教程理解、674条候选命令和一个8类教程视觉基线；该模型跨视频验证未通过，Windows 接口已实现但缺实机验收，当前仍无正式游戏检测模型或已验证实机策略。

## 从这里开始

| 要做的事 | 文档 |
|---|---|
| 看目前进度、下一步和验收条件 | [项目路线](../roadmap.md) |
| 安装 Linux/Windows、配置游戏窗口和迁移数据 | [双平台使用说明](../windows-linux.md) |
| 开发插件、修改代码和提交工作区 | [开发流程](development.md) |
| 理解模块、数据流和版本边界 | [架构说明](../architecture.md) |
| 增加游戏适配器或替换模型 | [插件接入](../plugins.md) |
| 下载教程、读取语义和比较速度 | [视频阶段](../video-stage1.md) |
| 把原神教程语音转换为可复核命令 | [语音转候选游戏命令](../voice-command-stage2.md) |
| 复核 P10 的候选语义命令 | [P10 候选命令复核表](../reviews/BV1P6SNYREo8/P10.md) |
| 训练 YOLO 并从 Windows 实时画面形成稳定游戏状态 | [原神实时感知方案](../genshin-realtime-perception.md) |
| 查看原神教程基线训练节点、数据隔离和当前进度 | [YOLO 训练计划与进度](../genshin-yolo-training-plan.md) |
| 区分视觉训练、动作经验和后续行为克隆 | [记忆与训练](../learning.md) |
| 查看实测结果及限制 | [验证记录](../validation.md) |
| 了解项目内 Codex 技能 | [技能适配检查](../skills-audit.md) · [项目技能](../../.agents/skills/game-agent-gpt6/SKILL.md) |

## 原神视觉基线索引

| 产物 | 入口与状态 |
|---|---|
| 实时感知设计 | [原神实时感知方案](../genshin-realtime-perception.md)：YOLO、OCR、跨帧状态融合与规划器边界 |
| 训练计划与节点 | [YOLO 训练计划](../genshin-yolo-training-plan.md)：GY0–GY7 进度、数据隔离、指标和限制 |
| 训练元数据 | [训练报告 JSON](../reports/genshin-ui-yolo26n-v1-training.json)：类别、参数、数据与权重哈希、Ultralytics 指标 |
| 独立验证结果 | [评估报告 JSON](../reports/genshin-ui-yolo26n-v1-evaluation.json)：P10/P13 逐帧结果、逐类召回和完整教程回放 |
| 版本化权重 | [模型说明](../../models/README.md)：5.12 MiB、SHA-256、适用范围和已知失败 |
| Windows 加载配置 | [原神 Windows 示例](../../configs/genshin-windows.example.toml)：默认 dry-run，指向版本化权重 |
| 汇总验证结论 | [验证记录](../validation.md)：代码回归、训练证据、迁移包和待验证项 |

## 使用者和开发者共用的边界

- 教程输出是候选语义；Plan 是经过结构校验的候选执行计划；实际运行后观察到成功才形成相应模式的有效经验。
- 视频标注训练的是视觉模型。视频中看见动作不等于拿到了真实按键、鼠标轨迹和事件时序。
- 默认保留原始视频和分类；抽帧/标注是显式的后续操作。运行数据、模型和数据库保存在本项目 `memory/`。
- 实机操作由当前窗口观测驱动，不能直接重放教程坐标。Windows 示例默认 dry-run。

## 文档维护

新阶段开始或完成时更新 [路线](../roadmap.md)；新增/替换模块时更新 [架构](../architecture.md) 或 [插件](../plugins.md)；命令变化更新对应使用文档；测试结果更新 [验证记录](../validation.md)。本 Wiki 负责导航和开发约定，不复制所有命令，避免多个版本相互矛盾。

开发决策与事实写入 [项目记忆](../../memory/project.md)。代码、示例、Wiki 与路线同步提交；视频、数据集和运行数据库通过独立数据包迁移。经过明确选择的小型发布权重可以随仓库版本化，并在本 Wiki 记录大小、哈希和验证边界。项目根目录 [README](../../README.md) 保留面向使用者的索引。
