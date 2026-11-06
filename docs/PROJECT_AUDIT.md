# StarDrive 项目审计

2026-11-06 初审，源码基线为 `main@541222b`。范围包括功能入口、本地及 OSS 存储驱动、迁移、测试、镜像与公开 CI。复现使用临时 SQLite、本地样本和回环地址。

StarDrive 面向自托管个人和小团队，优先完善浏览器内的上传、管理、预览和限时分享。当前交付边界为单进程、单活存储。入口和验收范围见 [架构](ARCHITECTURE.md)、[功能清单](FEATURE_INVENTORY.md) 与 [场景](USER_SCENARIO_TESTS.md)。

## 审计结果

| ID | 审查范围 | 后续工作 |
| --- | --- | --- |
| AUD-01 | 分享授权 | 单独评审公开入口、访问码、路径范围与撤销。SD-01 |
| AUD-02 | 首次安装 | 用空目录验证管理员交付与首次登录，再验证重启。SD-02 |
| AUD-03 | 依赖 | 对锁定运行时依赖执行漏洞扫描，公告去重后按可达性分诊。SD-03 |
| AUD-04 | 批量下载 | 为多选归档补齐持久化、内容比对和失败反馈。SD-06 |
| AUD-05 | 历史数据库 | 初审发现部分历史库升级未通过。用真实历史版本生成的样本验证识别、备份、升级和恢复。SD-04 |
| AUD-06 | 本地覆盖 | 对中断、取消和成功替换分别验证文件内容和清理。SD-05 |
| AUD-07 | 交付与启动 | 基线 Quality 配置未通过 GitHub 校验。Quality 已恢复，分支 push、PR 与 Docker 冒烟通过。启动探针和目录配置另验。SD-07 |
| AUD-08 | 会话与存储 | 验证会话撤销、账号停用和存储档案切换。SD-08 |
| AUD-09 | 资源与网络 | 测量并发、超时和临时盘用量，验证请求取消和网络故障。SD-08 |
| AUD-10 | 普通下载 | 验证未配置 Service URL 的站内私有下载。SD-07 |
| AUD-11 | 安全默认与日志 | 复核首装配置、日志脱敏和部署边界。SD-02、SD-08 |
| AUD-12 | 可维护性 | 逐步补齐浏览器回归、恢复手册和候选版本验收。SD-06、SD-07 |

工作流校验和历史失败可对照 [GitHub Secrets 规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets) 及 [基线 Quality 运行](https://github.com/qqAys/StarDrive/actions/runs/29215733256)。未披露的安全发现与复现按 [安全报告流程](../SECURITY.md) 私下跟踪。

## 优先推进

先验收分享、首登、历史库升级、上传覆盖和依赖风险，再把日常文件操作纳入可重复门禁。逐项状态见 [路线图](ROADMAP.md)，发布条件见 [生产就绪检查](PRODUCTION_READINESS.md)。
