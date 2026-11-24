# S3 管理台阶段验收记录

基线为 `105330e7bfa6334f46532e68a1cce1a2dcde690a`。本阶段复用单进程、SQLite、
现有 Fernet 凭据格式和 Local/OSS 用户对象布局，无数据库 schema 迁移。单活是兼容现状，
统一挂载与已有文件接入继续独立推进。发布状态以对应 PR 和运行器回执为准。

## 实现及恢复边界

S3 档案支持 endpoint、region、bucket、前缀与逐字段加密凭据。私有端点需管理员明确指定；
仅管理员主动测试时在 `.stardrive-probes` 创建唯一合成对象并读回、清理，固定错误反馈不显示
服务端异常或凭据。保存档案须测试成功才可激活，修改配置清除原测试结果；激活及重启不探测。

探测、更新及激活串行。取消不能停止 SDK 工作线程，因此等待其完成清理再释放锁；
取消不持久化成功。确认后重新验证活跃管理员，失败激活保留原档案。管理台在窄屏上下排列，
S3 表单及详情操作使用原生响应式网格；没有新增浏览器组件或应用运行依赖。

## 回归与独立浏览器证据

前次通用门禁为 311 passed、2 deselected，Black/Babel 通过；独立复核因缺少浏览器证据拒绝。
本次保留该候选及回归，新增可重放浏览器套件；当前修改后的通用门禁和专项以新运行器回执为准。

2026-11-24 使用锁定 NiceGUI 3.11.1 和应用环境的 boto3 1.44.9，通过真实 Chromium、真实
临时 SQLite 及回环 Moto 5.2.6 协议服务执行。UI 组件、授权装饰器、档案服务、文件工厂和
驱动均为当前应用源码；模拟服务仅提供合成 HTTP 对象存储及受控故障，不是真实外部 S3。

pytest 节点：`tests/test_s3_console_browser.py::test_s3_console_browser`。
该入口已实际执行并通过（1 passed，106.72 秒），包含桌面 1280px 和窄屏 390px 各 13 场景，
本次定义场景完成率 26/26（100%，每场景每视口一次；不是用户完成率或统计性能结论）：

- 管理员原 Local 文件下载；无效端点拒绝、S3 草稿测试、保存后测试、激活及完整应用重启。
- 两个独立浏览器用户分别上传、预览和下载，核对 SHA-256，互不可见；切回 Local 后原文件摘要不变。
- 权限不足、清理失败均阻止新激活并保留原档案；恢复权限、重测后可激活。
- 两个管理页面同时探测与编辑：编辑等待探测清理，旧成功结果失效，重新测试才可激活。
- 探测期间实际浏览器断网，线程完成对象清理并保存结果；重连后重新进入管理台可恢复操作。
  此场景验证持久化结果和重新进入，不声称弹窗原位保留。
- 已打开页面的管理员被撤权或停用后，保存回调拒绝；普通用户不能进入管理台。
- 表单 Tab 焦点、Enter 保存、页面无横向溢出及窄屏内容区宽度；逐视口截图已查看。
- 最终清空合成 bucket；应用日志、SQLite 文件及重新加载后的页面不含明文合成 S3 凭据。

套件记录实际输入、点击、按键和导航调用数量及耗时，不记录输入内容。下表为本次场景从开始
到全部断言结束的墙钟秒数，包含导航、等待和故障注入；没有历史同场景基线，不推断性能提升：

| 场景 | 桌面秒 | 390px秒 | 浏览器操作数（桌面/窄屏） |
| --- | ---: | ---: | ---: |
| configure-test-activate | 4.293 | 4.315 | 21 / 21 |
| upload-preview-download | 2.169 | 1.858 | 10 / 10 |
| permission-cleanup-failure-recovery | 6.396 | 6.730 | 12 / 12 |
| concurrent-test-edit-invalidates-result | 5.564 | 6.008 | 11 / 11 |
| disconnect-probe-cleanup-and-recover | 4.489 | 5.183 | 7 / 7 |

配置场景包含一次无效端点修正、草稿和保存后探测；失败恢复包含权限拒绝及清理失败两次注入。
并发与断网场景各注入 2 秒探测延迟。具体定义、每次操作、结果和源码 SHA-256 均由脚本产出。

复跑方法见 `tests/browser/README.md`；浏览器/Moto 只装入独立工具环境。测试默认不属于普通
非外部门禁，必须显式选择 external 节点并配置工具 Python；缺少工具导致跳过不能视作通过。
每次使用新临时数据目录、随机合成凭据及仅回环可用的受保护 fixture 控制入口，禁止用于部署。

## 本轮专项回执修复

上轮专项执行为 `27 passed, 1 deselected`：运行器固定使用 `-m 'not external'`，
而专项清单包含上述 external 浏览器节点，故回执缺少该节点。此结果不是浏览器测试失败，
也不能将排除视为执行通过。本轮保留应用、浏览器脚本、external 标记和依赖文件；
与本轮输入的 102 个 SHA-256 指纹逐一比对，均一致。独立浏览器原始回执为
`manual-s3-console-recovery-20261124/browser-release.log`，结果目录为同级
`browser-release/`；其中 26 条结果全部通过，summary 中的应用源码指纹也与当前树一致。
该证据与运行器非 external 专项分别审阅，不以历史复核结论代替本轮复核。

运行器专项清单只应选择可在其既定命令中执行的回归，例如：

| 风险 | 非 external 节点（可与原有共享契约回归合并执行） |
| --- | --- |
| 写入及恢复 | `tests/test_storage_config_service.py::test_s3_probe_unique_cleanup_and_sanitized_errors`；`tests/test_storage_config_service.py::test_concurrent_s3_test_edit_cannot_certify_changed_profile`；`tests/test_storage_config_service.py::test_s3_profile_secret_merge_activation_failure_restart_and_return` |
| 存储 | `tests/test_storage_provider_compatibility.py::test_s3_persisted_encryption_restart_and_local_restore`；`tests/test_s3_storage.py::test_shared_archive_range_and_user_isolation` |
| 输入与授权 | `tests/test_storage_config_service.py::test_s3_rejects_endpoint_before_network`；`tests/test_storage_config_service.py::test_s3_rejects_redirect_destination_before_sending`；`tests/test_s3_console_callbacks.py::test_actual_saved_profile_callbacks_recheck_permissions`；`tests/test_s3_console_callbacks.py::test_actual_activate_callback_rechecks_after_confirmation` |
| 运行兼容 | `tests/test_storage_provider_compatibility.py::test_persisted_old_profiles_restart_blank_secret_failure_and_switch`；`tests/test_storage_provider_compatibility.py::test_provider_build_keeps_user_prefix_and_stream_bytes`；`tests/test_version.py::test_app_version_comes_from_package_metadata` |

这些回归不替代浏览器验收。浏览器节点仍按上节独立显式执行，不能加入固定排除
external 的必跑清单；未修改运行器、门禁或测试断言。

本轮本地验证使用锁定依赖及 `/private/tmp/stardrive-model-02824d9h` 合成数据目录
（同时设置现有路径模块使用的 `STARDIVE_APP_DATA_DIR` 和配置项
`STARDRIVE_APP_DATA_DIR`）。上述相关六个测试文件共 67 项通过，无跳过或排除；
Black 检查 134 个文件通过，Babel 编译及 diff 空白检查通过。
全量非 external 回归为 310 passed、1 skipped、3 deselected：SMTP 本地测试因当前
沙箱不允许绑定监听端口而跳过，不能计为通过，须由运行器在支持监听的环境重跑。
本轮未重跑 Chromium，浏览器完成率、操作数与等待时间沿用上节已核验的独立原始回执，
没有新增体验测量或真实服务测量。

## 后续环境验收

浏览器脚本过滤宿主 StarDrive/NiceGUI 配置，并从独立输出目录启动应用，拒绝读取其中的
`.env`；输出目录仅链接当前源码的 migrations，以保留应用现有的相对 Alembic 路径。
隔离调整后的上述 26 场景已通过新 pytest 入口完整重跑。测试源位于普通 tests 目录，
没有改动研发运行器、GitHub 工作流或已有真实服务测试，也不读取 CI 凭据。

上述是本地合成服务验收。真实 S3 兼容服务、真实 OSS/SMTP、容器内完整 S3 交互、
生产部署和旧版本代码实际降级尚未执行。恢复顺序见 OPERATIONS.md：先切回并验证原档案，
停服备份数据库、稳定应用密钥和配置，再回退 S3 入口，保留对象及可恢复配置。
