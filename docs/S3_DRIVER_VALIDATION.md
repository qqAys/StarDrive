# S3 第二阶段验证记录（本地候选）

基线：本轮输入 `0553b2e7c99b62317491fa633adbc0a48cadebe9`，分支
`ai/feat/storage-provider-expansion-s2`，当前 HEAD 与输入基线一致。
本轮接手时已有暂存和未暂存的阶段候选（包括锁文件补齐），继续保留并核验；
本地 main 为 `541222b`，落后于该基线，不将其差异计入本轮交付。
未提交、推送或部署。

## 范围与兼容

仅新增显式构造的驱动、依赖声明、合成测试与文档。未更改提供者注册、档案持久化、
加密、UI 或 Local/OSS 行为。复用 OSS 驱动的路径、元数据、列表与搜索编排，
覆盖其所有 SDK 入口，避免复制两套虚拟目录语义；未来公共抽取可单独实施。
单进程和 SQLite 不影响本阶段驱动接入，无数据库迁移。

## 前轮记录

- Python 语法编译、`git diff --check`：通过。
- `uv add --no-sync boto3`：默认缓存不可写；改用 `/private/tmp/stardrive-uv-cache`
  后 PyPI DNS 失败，未能生成锁文件。
- 离线同步：临时缓存缺少 aiosqlite 等依赖，失败。
- pytest：环境中没有 pytest，未执行用例。
- Black：环境中没有 Black，未格式化；由运行器格式化本阶段 Python 文件。
- 完整 pytest、Babel、真实 S3/OSS、Docker、浏览器、代码回退：未执行。

上次开发时 `pyproject.toml` 已声明 boto3，但 uv.lock 尚未同步，随后运行器的 locked 门禁因此失败。
当前候选锁文件已补齐 boto3 及其传递依赖，保留原有包版本。

## 本轮失败修复核验（2026-11-23）

读取输入指定的前轮 `tests.log`：运行器在 `uv sync --locked --all-groups`
阶段报告锁文件需要更新，尚未进入测试。

- `UV_CACHE_DIR=/private/tmp/stardrive-uv-cache uv lock --check --offline`：通过，
  解析 96 个包，确认当前 pyproject 与锁文件一致，前轮锁文件失败点已修复。
- 指定 `UV_PROJECT_ENVIRONMENT=/private/tmp/stardrive-model-udhn9xcj/venv`
  的 `uv sync --locked --all-groups --offline`：锁定解析通过，安装因缓存缺少
  `jinja2==3.1.6` wheel 失败。由运行器安装锁定依赖，不扩大网络或文件权限。
- 暂存区及未暂存区的 `git diff --check`：通过。
- pytest、Black、Babel：因依赖未安装未执行；合成回归沿用下述用例，
  由运行器格式化本阶段 Python 文件并执行完整门禁。
- 真实 S3/OSS、Docker、浏览器和代码回退：未执行。

锁文件检查是前轮失败的直接回归检查，不代替驱动契约或阶段验收。

## 合成回归与复跑

统一设置 `STARDIVE_APP_DATA_DIR=/private/tmp/stardrive-model-s1n9edqp`
（源码 paths.py 当前环境变量拼写为 STARDIVE），另设置同目录的
`STARDRIVE_APP_DATA_DIR`，使用临时合成应用密钥，不创建 .env。
依赖齐备后运行：

```sh
uv run --locked pytest tests/test_s3_storage.py tests/test_archive_backends.py tests/test_storage_provider_compatibility.py tests/test_aliyun_oss_storage.py tests/test_multi_user.py
```

内存协议客户端覆盖多页、Unicode、空目录、零字节、共享归档摘要、Range 和读取关闭、
跨用户路径拒绝、分页停滞、分段失败与取消清理、重传摘要、复制失败保留源、
删除失败保留副本及重试。另有 boto3 构造参数与错误映射测试，未使用真实凭据。
正常与故障契约完成率：**未测**，测试尚未运行，不能提供通过比例。

## 场景指标

环境：本机隔离工作树，Python 3.12.13 可用；无项目已安装依赖，无外部连接。
样本：中文目录、é.txt、两个小文件、空目录、零字节对象和另一用户对象；
分段恢复以缩小分段阈值的合成样本执行，不声称真实服务接受该阈值。
方法：比较 Local/S3 归档条目与 SHA-256；正常上传后读取摘要；注入生产者失败、
分段失败、取消、复制失败与删除错误后核对源、目标及未完成上传状态，再重试。
目标：所有契约与原后端回归通过。当前结果：待运行器执行。
首屏、交互等待、操作步骤、浏览器完成率和失败恢复耗时均未测；本阶段不开放 UI，
独立浏览器配置闭环属于第三阶段。测试执行时长不作为体验指标。

## 本轮 pytest 修复（2026-11-23，repair-1 反馈）

读取本轮输入及指定的 `repair-1/tests.log`、候选差异和开发结果。运行器前次结果为
282 通过、1 失败、2 排除；Black 通过。唯一失败发生于
`test_shared_archive_range_and_user_isolation` 的本地归档基准准备阶段：
`StorageManager` 默认注册 Local，但不自动选中它，抛出 `BackendNotFoundError`。
本轮在测试中显式选择 `LocalStorage.name`，与既有共享归档夹具一致；
随后仍显式切换 S3，并比较完整归档清单与摘要。未改变服务默认选择行为，
避免影响现有调用者的显式后端选择契约；原有 Range、分页、空目录、零字节、
Unicode 和跨用户拒绝断言全部保留。

本轮本机核验：锁定离线同步解析 96 包成功，但临时缓存缺少
`starlette==0.50.0`，安装失败。环境目录为
`/private/tmp/stardrive-model-s1n9edqp/venv`，未访问真实服务或凭据。
pytest、Black、Babel 本轮尚未执行，由运行器安装锁定依赖后重跑完整门禁；
前次 282 项通过不作为修复后通过证据。正常与故障契约完成率仍待重测，
真实服务与浏览器体验指标仍未测。


## 独立复核修复（repair-2）

已读取输入指定的 review.json、tests.log 和前轮开发结果。运行器前次门禁
283 通过、2 排除，Black/Babel 通过；这些结果不代表本次修复后通过。
本次修复在任何复制前拒绝祖先目标，与既有相同路径、子目录拒绝一致；
保留非重叠目录复制后删除的行为，避免引入暂存迁移协议或改变对象布局。

新增回归：
- `test_move_rejects_overlapping_paths_before_copy`：祖先、子目录及相同路径，
  包含 a/b/x、a/b/b/x 和既有 a/x；验证未发生复制且全部字节不变。
- `test_directory_move_partial_deletion_retry_preserves_digest`：混合 Deleted/Errors、
  删除后缺失确认，以及 1002 个对象第一批成功、第二批部分失败。
  验证精确剩余源、完整目标副本，重试后源清空且全部目标 SHA-256 一致。

本次环境为本机 Python 3.12.13，隔离目录
`/private/tmp/stardrive-model-61wh1w8g`，合成样本仅使用内存客户端。
离线 `uv sync --locked --all-groups` 解析 96 包成功，但缓存缺少
`nicegui==3.11.1`，依赖安装失败；不访问外部网络，由运行器安装锁定依赖、
格式化 Python 并执行完整门禁。本次语法解析及 diff 空白检查通过。
新增契约完成率待运行器重测，真实 S3/OSS、Docker、实际代码回退未验证。
操作步骤、首屏、交互等待、浏览器完成率与失败恢复耗时仍未测；
本阶段未开放 UI，浏览器闭环仍属于第三阶段，不能用测试时长替代体验证据。
