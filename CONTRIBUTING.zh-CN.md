# 贡献给 StarDrive

我们很高兴您有兴趣为 StarDrive 贡献力量！

[English](https://github.com/qqAys/StarDrive/blob/main/CONTRIBUTING.md)

## 关于本项目

StarDrive 是一个基于 [NiceGUI](https://github.com/zauberzeug/nicegui) 库开发的网盘系统，提供多后端存储的文件管理功能。

### 项目结构

- `locales/` - 翻译文件
- `models/` - 模型定义
- `static/` - 静态资源
- `storage/` - 存储后端实现
- `tests/` - 测试
- `ui/` - 使用NiceGUI构建的前端代码

### 技术栈

这里部分引用了 NiceGUI 的技术栈：

- **Python 3.12+** - 核心语言
- **NiceGUI**

  - **FastAPI/Starlette** - Web 框架
  - **Vue 3** - 前端框架
  - **Quasar** - UI 组件框架
  - **Tailwind CSS 4** - 样式
- **pytest** - 测试框架
  

## 报告问题

如果您在使用 StarDrive 时遇到 Bug 或其他问题，最好的报告方式是在我们的 [GitHub 仓库](https://github.com/qqAys/StarDrive) 中开启一个新的 issue。

1. Bug：请按照 [BUG模版](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_TEMPLATE/bug_report.md) 填写

2. Feature：请按照 [Feature模版](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_TEMPLATE/feature_request.md) 填写

3. Question / Support：请按照 [Question模版](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_TEMPLATE/question-or-support.md) 填写

## 行为准则

我们遵循 [行为准则](https://github.com/qqAys/StarDrive/blob/main/CODE_OF_CONDUCT.md) 以确保所有参与 StarDrive 的人都感到受欢迎和安全。

如果您参与讨论与贡献，代表您同意遵守其条款。

## 贡献代码

### 环境准备

要为 StarDrive 设置本地开发环境，您需要安装 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

您可以使用以下命令安装 uv：

macOS/Linux:
```shell
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows:
```shell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

确保已安装 uv 后，您可以使用以下命令安装 StarDrive 的依赖项：

```shell
uv sync
```

### 编码风格

StarDrive 使用 [Black](https://github.com/psf/black) 来格式化代码。

您可以使用以下命令来格式化代码：

```shell
uv run black .
```

### 测试

StarDrive 使用 [pytest](https://docs.pytest.org/en/latest/) 来构建测试。

在提交拉取请求之前，请确保所有测试都通过。要在 StarDrive 的根目录中运行所有测试，请使用以下命令：

```shell
uv run pytest
```

### 翻译

1. 本项目使用 `pybabel` 创建翻译文件 `.pot`：

    ```shell
    uv run pybabel extract -F babel.cfg -o locales/messages.pot .
    ```

2. 初始化 `.pot` 文件后，创建你要翻译的语言文件

    ```shell
    uv run pybabel init -i locales/messages.pot -d locales -l {你的语言代码}
    ```

3. 使用你喜欢的编辑器打开 `.po` 文件，在 `msgstr` 中填写翻译。

4. 生成语言文件 `.mo` 进行测试

    ```shell
    uv run pybabel compile -d locales
    ```

5. 测试无误后，将 `locales/{你的语言代码}/LC_MESSAGES/messages.po` 提交到版本控制系统。请注意，遵守 `.gitignore` 文件，不要提交 `.pot` 与 `.mo` 文件。


### 创建拉取请求

创建拉取请求时，请确保您遵循以下步骤：

1. 创建一个 fork，并克隆到您的本地。

2. 基于 `main` 创建一个功能分支，基于您的 fork 的主分支。（例如：`feat/my-new-feature`、`fix/bug-description`、`docs/update-readme`）。

3. 添加您的更改并提交。

4. 进行代码格式化与测试。

5. 推送您的更改到您的 fork。

6. 创建一个拉取请求，按照 [拉取请求模版](https://github.com/qqAys/StarDrive/blob/main/.github/PULL_REQUEST_TEMPLATE.md) 填写，附上您更改的详细描述，并等待我们进行合并。

提交拉取请求时，请确保代码遵循现有的编码风格，并且所有测试都通过。如果您要添加新功能，请包含涵盖新功能的测试。

## 致谢

向所有为 StarDrive 贡献代码的贡献者们致以诚挚的谢意！
