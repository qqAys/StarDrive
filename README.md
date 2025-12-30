# StarDrive

<p align="center">
  <img src="https://img.shields.io/github/license/qqAys/StarDrive" alt="License">
  <a href="https://hosted.weblate.org/engage/stardrive/">
    <img src="https://hosted.weblate.org/widget/stardrive/stardrive/svg-badge.svg" alt="Translation status">
  </a>
</p>

StarDrive 是一个基于 [NiceGUI](https://github.com/zauberzeug/nicegui) 构建的云盘系统，支持多后端存储，并提供完善的文件管理功能。

StarDrive is a cloud drive system built on the [NiceGUI](https://github.com/zauberzeug/nicegui) library, featuring multi-backend storage support and comprehensive file management capabilities.

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
    curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
    ```
2.  **安装依赖并运行**:
    ```shell
    uv sync
    uv run -m app.main
    ```

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

## 致谢 (Acknowledgments)

本项目基于 [NiceGUI](https://github.com/zauberzeug/nicegui) 的杰出工作：

> Schindler, F., & Trappe, R. NiceGUI: Web-based user interfaces with Python. The nice way. https://doi.org/10.5281/zenodo.7785516

感谢所有为本项目付出努力的贡献者！

## 许可 (License)

本项目遵循 [MIT](./LICENSE) 许可证。