# 同类项目研究

2026-11-06 核对公开代码、文档、版本和近期问题记录。选择 FileBrowser Quantum 作为浏览器文件管理对标、OpenList 作为多存储参考、SFTPGo 作为传输与安全参考。以下为公开证据研究，未在本机部署三个项目或测量它们的性能。未核实的能力以“未核实”标记。没有复用外部源码。

## 参考项目

| 项目与场景 | 安装、扩展与安全 | 测试、发布及近期演进 |
| --- | --- | --- |
| FileBrowser Quantum。个人、NAS 和小团队管理挂载的本地文件，支持按源权限、索引搜索、带密码/过期/次数的分享和预览 | 单二进制或 Docker，YAML 定义文件源。文档描述 OIDC、LDAP、代理认证和可配置 API token，支持 Swagger。源和适配器可配置，通用插件市场与专用指标端点未核实 | `v2.0.2-stable`，2026-10-24 中国时间。PR 工作流将分享、OIDC 和代理场景分成 Playwright 项目。近期版本修复访问令牌权限与分享重定向，后续 PR 改善 Office 预览 |
| OpenList。集中浏览多个云盘和已有存储，适合多来源聚合和 WebDAV | Docker/二进制，按驱动挂载。源码将驱动契约放在 `internal/driver`，具体实现放在 `drivers/`。管理/集成 API 与 WebDAV，安装文档含首登及管理员重置。运维指标端点与驱动隔离未核实 | `v4.2.9`，2026-10-25 中国时间。包含 Docker 测试、Beta、正式发布和变更日志工作流。近期流式恢复和下载错误路径脱敏 PR 显示故障和泄露问题被单独处理 |
| SFTPGo。面向有外部客户端和自动化需求的运营者，集中提供浏览器、SFTP、WebDAV 等传输入口 | Docker/二进制，按用户设置目录、配额和后端，含 OIDC、登录防御、REST API、事件钩子、插件和 Prometheus 指标。WebClient 支持过期和受保护的分享 | `v2.7.6`，2026-09-19 中国时间。开发、Docker、CodeQL 和发布分离。版本记录修复停用用户的分享撤销和目录归档边界。近期配额问题与管理端 API key PR 对应实际维护方向 |

- Quantum：[配置与升级](https://filebrowserquantum.com/en/docs/getting-started/config/)、[文件源](https://filebrowserquantum.com/en/docs/configuration/sources/)、[官方功能文档](https://filebrowserquantum.com/)、[PR 工作流](https://github.com/gtsteffaniak/filebrowser/blob/main/.github/workflows/pr.yaml)、[发布记录](https://github.com/gtsteffaniak/filebrowser/releases/tag/v2.0.2-stable)、[Office PR](https://github.com/gtsteffaniak/filebrowser/pull/3335)。
- OpenList：[Docker 安装](https://doc.oplist.org/guide/installation/docker)、[驱动契约](https://github.com/OpenListTeam/OpenList/tree/main/internal/driver)、[发布与测试流程](https://github.com/OpenListTeam/OpenList/tree/main/.github/workflows)、[发布记录](https://github.com/OpenListTeam/OpenList/releases/tag/v4.2.9)、[传输 PR](https://github.com/OpenListTeam/OpenList/pull/3323)、[分享错误 PR](https://github.com/OpenListTeam/OpenList/pull/3322)、[社区讨论](https://github.com/OpenListTeam/OpenList/discussions)。
- SFTPGo：[Web 界面](https://github.com/sftpgo/docs/blob/main/docs/web-interfaces.md)、[容器](https://github.com/sftpgo/docs/blob/main/docs/docker.md)、[指标](https://github.com/sftpgo/docs/blob/main/docs/metrics.md)、[HTTP 实现与测试](https://github.com/drakkan/sftpgo/tree/main/internal/httpd)、[工作流](https://github.com/drakkan/sftpgo/tree/main/.github/workflows)、[发布记录](https://github.com/drakkan/sftpgo/releases/tag/v2.7.6)、[配额 Issue](https://github.com/drakkan/sftpgo/issues/2303)。

## 功能差距

| 领域 | StarDrive | Quantum | OpenList | SFTPGo | 重要程度与取舍 |
| --- | --- | --- | --- | --- | --- |
| 首次管理员与恢复 | 凭据交付受阻 | 可配置管理员和初始化参数 | 提供 CLI 恢复 | 初始设置与管理员配置 | P0 补全 |
| 文件与批量传输 | 单文件支持，批量归档有缺陷 | 文件浏览、批量与归档 | 主要面向挂载与代理 | WebClient 与多协议 | P1 先补齐批量闭环 |
| 保护分享 | 端到端验收待完成 | 密码、次数、时效、权限范围 | 分享能力有实现 | 时效、权限与停用撤销 | P0 补全服务端约束 |
| 多后端与切换 | 本地/OSS 单活档案 | 多个文件源 | 多驱动同时挂载 | 按用户配置与虚拟目录 | P1 补档案边界，P2 按需求评估新增后端 |
| 恢复与诊断 | Alembic 与存活探针，恢复待验 | 版本迁移指南、活动数据 | 持久数据卷与安装升级指引 | 日志、指标与维护接口 | P0 历史恢复，P1 诊断 |
| 内容预览 | 文本、媒体、PDF、LibreOffice | 预览和 Office 支持 | 缩略图、媒体与部分驱动代理 | 以传输为主，Office 未核实 | P2 保留并限制资源 |
| API、协议与身份 | 有内部端点，暂无稳定文件 API | Swagger、API token、多认证 | WebDAV、驱动与 API | REST、SFTP、WebDAV、OIDC | P3 暂缓 |
| 自动化发布 | CI 检查与发布流程待验 | PR 按场景分组，分阶段发布 | 测试、Beta、changelog | 开发、镜像、CodeQL、发布分离 | P1 借鉴职责分离 |

## 取舍依据

| 分类与缺口 | 用户价值与缺失影响 | 最小实现、成本与路线 |
| --- | --- | --- |
| 必须补齐。首登、授权、上传覆盖和恢复 | 新用户需要从零获得可用实例，接收者只应取得授权字节，失败或升级后仍能找回文件 | 沿现有账户服务、令牌验证、存储驱动和 Alembic 增强。中等成本，持续保留可复跑样本。SD-01～05 |
| 重要体验。批量归档、配置诊断、浏览器门禁 | 多选下载与部署排障是日常任务。无明确错误会导致重试和放弃 | 先恢复已有操作及错误反馈，加入单个真实浏览器场景；暂用顺序处理与明确状态。中等成本。SD-06/07 |
| 差异化候选。OSS 与低成本预览 | 现有 OSS 使用者可能希望就地预览、临时分享；用户需求仍是推断 | 保留单活及现有浏览器体验，先补真实 OSS 与转换限制。比多云同时挂载更易维护。SD-08/09 |
| 可选高级能力。稳定 API、OIDC 或 WebDAV | 有自动化、身份联邦或挂载需求时才有价值。当前小团队浏览器路径仍可完成多数任务 | 收集具体调用方和权限要求后一次只交付一项。兼容及长期支持成本高。SD-10 |
| 当前不适合。桌面同步、通用插件市场、协作编辑、多副本 | 对当前核心闭环帮助有限，显著增加数据冲突、权限和交付成本 | 保持简单的单实例和现有驱动接口。出现可验证需求再重开架构决策 |

治理上先引入按风险分离的测试和发布门禁。竞品的大规模矩阵、插件或协议组合不直接移植。
