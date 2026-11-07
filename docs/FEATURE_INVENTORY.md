# 功能清单

审计基线为 `541222b`，基线范围见 [审计](PROJECT_AUDIT.md)。服务层、浏览器、真实 OSS 和正式部署分别验收。

| 能力 | 入口和调用链 | 状态与证据 |
| --- | --- | --- |
| 初次安装与管理员 | `app.main → on_startup → init_local_db → UserManager.initialize` | 部分实现。空库创建和初始管理员交付分别验收，首次安装尚未通过 |
| 登录、注册、个人设置 | `ui/pages/{login,account,profile}.py → UserManager → UserCRUD` | 浏览器登录和文件页已验证，测试使用临时预置凭据。注册开关、停用、会话撤销有服务层覆盖，已打开页面撤销待验证 |
| 管理台 | `ui/pages/console.py → 用户、主题、存储档案服务` | 管理员可打开。主题和档案配置有测试，批量账户操作及低权限绕过矩阵待浏览器验证 |
| 找回密码 | 公开表单和 `/api/auth/*` → `UserManager → PasswordResetTokenCRUD / SMTP` | 本地 SMTP 送达和过期拒绝已测。真实 SMTP、并发消费和失败恢复待验证 |
| 本地文件 | `/home/ → FileBrowserTable / Dialog → StorageManager → LocalStorage` | 支持目录、浏览、搜索、上传、移动、重命名、删除、元数据和下载。存储测试及浏览器样本见 [场景](USER_SCENARIO_TESTS.md)。复制有后端接口，文件页无对应入口 |
| 批量文件操作 | `FileBrowserTable` 多选 → 移动、删除或压缩下载 | 部分实现。批量归档的列表与数据库字符串字段不匹配，失败行为见审计 |
| 分享 | 文件详情 → 分享记录和签名链接 → `/share/{token}` → 文件或目录下载 | 提供限时分享、访问码和目录浏览入口。授权隔离、撤销和真实 OSS 验收见 SD-01、SD-08 |
| 文件预览 | `MediaDialog → /api/preview-file/*`，Office 走 LibreOffice | 类型覆盖图片、媒体、PDF、文本、Markdown、表格和 Office。类型、缓存键有测试。真实大文件、异常文件、并发转换和容器 Office 待验 |
| OSS | 管理台 → `StorageConfigService → AliyunOSSStorage` | 有模拟客户端和档案测试。连接检查为 Bucket 信息读取，实际对象读写及 multipart 契约待验；大文件上传先落临时盘 |
| 多后端 | 多个档案，单个实例选定一个全局活跃后端 | 档案持久化及切换有测试。没有挂载聚合、在线迁移或历史链接的档案绑定 |
| HTTP API | 健康、下载、预览、登录、注册、密码重置 | 有路由。登录 API 签发 JWT，但没有刷新端点或通用文件管理 API。浏览器会话与 API JWT 用途不同 |
| 运维交付 | Compose、CalVer、Alembic、滚动日志、探针、Quality 工作流 | 基线提供存活探针。就绪探针由 SD-07 独立交付。镜像、真实升级和恢复门槛见 [生产就绪](PRODUCTION_READINESS.md) |

明确缺失且需要评估的能力包括首次管理员凭据交付与恢复、故障安全的上传覆盖、可信的备份恢复和受控的公网暴露。跨设备同步、协作编辑、多副本、公共插件市场和企业 IAM 暂不纳入当前产品目标。

## 当前目录名称过滤（本地候选）

`/home/ → FileBrowserTable` 的工具区提供可清空的名称输入，按当前已加载条目的原始名称进行不区分大小写的字面片段匹配。切换目录重置条件，输入变化重置页码并移除隐藏项选择。递归名称搜索继续使用原搜索按钮。新增回归用例待运行器执行，浏览器、本地及真实 OSS 验收待完成。
