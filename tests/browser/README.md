# S3 管理台隔离浏览器验收

此套件启动当前源码的完整 NiceGUI 应用、独立临时 SQLite、两个合成用户和仅监听
回环地址的 Moto S3 协议模拟服务。应用通过锁定的 boto3 实际发送 HTTP 请求；不替换
UI 组件、授权装饰器、档案服务或文件工厂。它不访问真实 S3、OSS、SMTP 或生产数据。

先安装项目锁定依赖，再在独立工具环境安装浏览器依赖（不修改项目锁文件）：

```sh
uv sync --locked --all-groups
uv venv /tmp/stardrive-browser-tools --python 3.12
uv pip install --python /tmp/stardrive-browser-tools/bin/python 'playwright==1.65.2' 'moto[server]==5.2.6'
/tmp/stardrive-browser-tools/bin/python -m playwright install chromium
STARDRIVE_BROWSER_TOOLS_PYTHON=/tmp/stardrive-browser-tools/bin/python \
  uv run --locked pytest -m external tests/test_s3_console_browser.py
```

已有 Chromium 可通过 `STARDRIVE_BROWSER_CHROMIUM` 指定可执行文件。浏览器默认无头运行。
`STARDRIVE_BROWSER_OUTPUT` 可指定一个新的输出目录；已有测试数据库会被拒绝复用。
测试数据、日志、截图、逐场景结果及源码 SHA-256 保留在该目录，失败不会误报成功。
应用子进程从输出目录启动，不读取仓库 `.env`，并移除继承的应用与 NiceGUI 配置变量，
避免宿主的数据库、SMTP 或会话存储设置影响隔离样本。
凭据每次随机生成，不写入结果或日志；测试控制路由仅由专用 fixture 进程注册，并以
随机请求头保护。该 fixture 不可用于对外部署。

桌面 1280px 和窄屏 390px 各执行 13 场景：原 Local 下载、S3 配置/测试/激活、应用重启、
上传/预览/下载摘要、双用户隔离、切回 Local、原文件摘要、权限及清理失败恢复、
双管理页面并发测试/编辑、探测期间断网恢复、撤销管理员、普通用户、停用管理员。
保存使用实际 Enter 键，表单验证 Tab 焦点顺序。窄屏检查内容区宽度和页面无横向溢出。

结果中的 `seconds` 是从场景开始到全部页面/文件断言结束的墙钟时间，包括故障注入、
页面导航、等待和恢复；`operations` 记录实际浏览器输入/点击/按键/导航调用及耗时，
不记录输入内容。它们是该合成环境的描述性测量，不是生产性能或真实服务验收。
模拟清理失败会暂留唯一探测对象，套件最后清理并核对模拟 bucket 为空。
