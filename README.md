# <img src="app/static/android-chrome-512x512.png" width="20" height="20" /> StarDrive

<p align="center">
  <img src="https://img.shields.io/github/license/qqAys/StarDrive" alt="License">
  <a href="https://hosted.weblate.org/engage/stardrive/">
    <img src="https://hosted.weblate.org/widget/stardrive/stardrive/svg-badge.svg" alt="Translation status">
  </a>
</p>

StarDrive 是面向个人和小团队的自托管文件管理应用。通过浏览器上传、整理、预览和分享文件，管理员可在本地磁盘与阿里云 OSS 档案间切换。

StarDrive is a self-hosted web file manager for individuals and small teams, with local disk and Alibaba Cloud OSS backends.

> [!WARNING]
> **本项目仍在开发中，尚未发布正式版本。**
> StarDrive 尚未经过充分测试，可能包含未知的 Bug 或安全漏洞。**请勿将其用于存储重要数据或在生产环境中使用。**
>
> **This project is under active development. No official release yet.**
> It may contain unknown bugs or security vulnerabilities. **Please DO NOT use it for sensitive data or in production.**

---

## 技术栈 (Tech Stack)

StarDrive 采用了现代化的 Python 技术栈：

* **Python 3.12+**
* **NiceGUI** (FastAPI, Vue 3, Quasar, Tailwind CSS 4)
* **SQLModel** - 数据库 ORM
* **PyJWT** - 身份认证
* **uv** - 现代 Python 包管理工具

## 快速开始 (Quick Start)

本项目使用 `uv` 进行依赖管理。

1.  **安装 uv**:
    ```shell
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```
2.  **创建本地配置并生成密钥**:
    ```shell
    cp .env.example .env
    openssl rand -hex 32
    # 将输出填入 .env 的 STARDRIVE_APP_SECRET
    ```
3.  **安装依赖并运行**:
    ```shell
    uv sync --locked
    uv run --locked pybabel compile -d app/locales
    STARDRIVE_APP_HOST=127.0.0.1 uv run --locked -m app.main
    ```

首次安装请在部署者专用的交互终端启动。空库创建管理员时，终端只显示一次邮箱和临时密码。
打开 `http://127.0.0.1:8080/login/`，按页面要求修改密码，再用新密码登录。
在 Console → Overview 配置完整的 `Service URL`，再用小文件验证上传、下载和分享。
无交互终端的部署和临时密码丢失时，按本机恢复流程获取临时密码，详见 [运维指南](docs/OPERATIONS.md#首次管理员登录)。

容器同样要求设置稳定的 `STARDRIVE_APP_SECRET`。开发时可将其写入未提交的 `.env`，
然后运行 `docker compose -f docker-compose.build.yml up --build`。该配置只映射本机回环地址。
`GET /api/healthz` 检查 HTTP 存活。请另行验证登录和初始化。
更多配置、反代要求与排障见 [运维指南](docs/OPERATIONS.md)。

本地上传在完整接收并关闭暂存文件后替换目标，失败或取消保留原文件。覆盖需要额外磁盘空间，故障恢复及限制见 [本地上传](docs/OPERATIONS.md#本地上传与故障恢复)。

### 数据库升级与备份

启动时会自动执行 SQLite 迁移。首次启动会创建数据库。迁移前请停止写入并备份数据库、
文件、配置及密钥，再使用副本演练。当前无 Alembic 版本的部分真实旧库会被拒绝，详情见
[备份与恢复](docs/OPERATIONS.md#备份与恢复)。

### 可选的外部集成验证

本地质量门禁使用 `uv run --locked pytest -m 'not external'`，无需云端凭据。真实 OSS 和 SMTP 契约测试需要专用服务。GitHub Actions 只在主分支 push 或手动运行时检查测试凭据，配置完整才执行对应的外部测试。状态见 [路线图](docs/ROADMAP.md)。

## 版本与 Docker 发布 (Versioning and Docker releases)

StarDrive 使用日历版本号（CalVer）。当前版本为 **`2026.11.13`**，格式为
`YYYY.M.D`；同一天的补发版本在末尾增加序号，例如 `2026.6.23.1`。版本仅在
`pyproject.toml` 中维护；已安装的发行包会从包元数据读取，源码运行时则读取同一份
`pyproject.toml` 元数据。

构建镜像时使用以下命令，它会同时生成 `qqays/stardrive:2026.6.23` 与
`qqays/stardrive:latest`，并为镜像写入 OCI 版本元数据：

```shell
python scripts/build_image.py
```

需要推送时附加 `--push`。`latest` 仅为便利标签；生产部署请固定使用日期版本，
例如 `qqays/stardrive:2026.6.23`，以保证部署可复现。

## 文件预览 (File Preview)

在非批量模式下，点击或轻触文件行的眼睛按钮（“预览文件”）打开预览，也可用 Tab 聚焦按钮后按 Enter 或空格激活。目录不显示预览按钮。选中文件后按空格仍可快速预览，双击文件仍进入下载确认。

StarDrive 支持图片、视频、音频、PDF、文本/代码、Markdown、CSV/TSV 的在线预览。
Office 文档（如 doc/docx/xls/xlsx/ppt/pptx）会通过 LibreOffice 转换为 PDF 后预览。

Docker 镜像会内置 LibreOffice 和 Noto CJK 字体，以支持中文等 CJK 文档转换预览。
若你直接在本机运行 StarDrive 且未安装 LibreOffice，Office 文档会显示“不支持预览，
需要安装 LibreOffice”，不会影响其他格式预览。本机运行时如果中文显示为方框，
请安装可用的中文字体。

## 阿里云 OSS 后端

超级管理员可在“Console”中录入 OSS Region、endpoint、Bucket、AccessKey ID/Secret 和可选对象前缀，先执行连接校验，再切换当前存储后端。后端使用官方 `alibabacloud-oss-v2` SDK；SDK V2 默认采用 V4 签名，因此 Region 必填。凭据以应用的 `APP_SECRET` 派生密钥加密保存于本地数据库，生产环境必须设置足够强且稳定的 `APP_SECRET`。

启用 OSS 后，每位用户的数据位于 `可选前缀/users/{user_id}/`。服务端代理文件操作。上传先使用临时文件暂存，较大文件通过 OSS 分段上传；Office 预览也需要临时磁盘空间。

给 AccessKey/RAM 用户授予所选 Bucket 的对象读写、列举、复制和删除权限，以及 Bucket 信息读取权限用于连接校验。切换本地与 OSS 后端不会自动迁移任一后端的既有文件。

## 翻译 (Translations)

我们使用 Weblate 管理多语言翻译。欢迎加入！

We use Weblate to manage translations. Contributions to new or existing languages are highly welcome!

[https://hosted.weblate.org/projects/stardrive/](https://hosted.weblate.org/projects/stardrive/)

[![Translation status](https://hosted.weblate.org/widget/stardrive/stardrive/multi-auto.svg)](https://hosted.weblate.org/engage/stardrive/)

## 贡献 (Contributing)

无论是修复 Bug、添加新功能还是改进文档，我们都欢迎您的贡献！

Whether it's fixing bugs, adding features, or improving docs, your help is appreciated!

* **指南 (Guide)**: 请阅读我们的 [CONTRIBUTING.md](./CONTRIBUTING.md) 以了解环境搭建、代码规范和 PR 流程。
* **问题反馈 (Issues)**: 发现问题？请通过 [GitHub Issues](https://github.com/qqAys/StarDrive/issues) 告知我们。
* **安全报告**：[SECURITY.md](SECURITY.md)。
* **开发进度**：[功能清单](docs/FEATURE_INVENTORY.md)、[路线图](docs/ROADMAP.md)、[变更记录](CHANGELOG.md)。

## 致谢 (Acknowledgments)

本项目基于 [NiceGUI](https://github.com/zauberzeug/nicegui) 的杰出工作：

> Schindler, F., & Trappe, R. NiceGUI: Web-based user interfaces with Python. The nice way. https://doi.org/10.5281/zenodo.7785516

感谢所有为本项目付出努力的贡献者！

## 许可 (License)

本项目遵循 [MIT](./LICENSE) 许可证。

### 当前目录类型筛选

文件列表可选择全部条目、仅文件或仅文件夹，并与名称过滤组合。计数显示当前目录完整列表的匹配数和总数，涵盖所有分页。类型变化清空选择并回到首页，重置筛选恢复全部条目，切换目录重置条件。递归搜索仍由原搜索按钮进入。

### 多选下载

在文件列表选择文件或文件夹后点击下载，确认后生成一个 `tar.gz` 归档，保留相对当前目录的路径和空目录。下载链接仅供创建者登录后使用。源在开始前缺失会拒绝下载，生成中读取失败会中断传输，应重新下载并确认归档完整性。

本地与 OSS 使用相同归档规则。相同规范化路径只写入一次，选择目录及其子项时保留完整目录树，各条目以首次遍历到的位置为准。Unicode 名称和空目录保留。归档使用生成时读取到的内容，不提供文件快照；生成期间请避免修改源，下载失败后重新生成。

多选记录采用带版本号的载荷，已有单文件和目录下载记录继续可用。降级前先备份数据库并隔离 `file_downloads.type = MIXED` 的新增记录，旧版本无法读取该格式。详见运维指南。
