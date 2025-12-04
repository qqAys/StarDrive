# Contributing to StarDrive

We're thrilled you're interested in contributing to StarDrive!

[简体中文](https://github.com/qqAys/StarDrive/blob/main/CONTRIBUTING.zh-CN.md)

## About the Project

StarDrive is a cloud drive system developed based on the [NiceGUI](https://github.com/zauberzeug/nicegui) library, offering multi-backend storage and file management capabilities.

### Project Structure

* `locales/` - Translation files
* `models/` - Model definitions
* `static/` - Static assets
* `storage/` - Storage backend implementations
* `tests/` - Tests
* `ui/` - Frontend code built with NiceGUI

### Tech Stack

This partially inherits the technology stack of NiceGUI:

* **Python 3.12+** - Core language
* **NiceGUI**
    * **FastAPI/Starlette** - Web framework
    * **Vue 3** - Frontend framework
    * **Quasar** - UI component framework
    * **Tailwind CSS 4** - Styling
* **pytest** - Testing framework

## Reporting Issues

If you encounter a bug or other issues while using StarDrive, the best way to report it is by opening a new issue in our [GitHub repository](https://github.com/qqAys/StarDrive).

1.  **Bug**: Please follow the [BUG Template](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_BUG_REPORT_TEMPLATE.md)

2.  **Feature**: Please follow the [Feature Template](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_FEATURE_REQUEST_TEMPLATE.md)

3.  **Question / Support**: Please follow the [Question Template](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_QUESTION_SUPPORT_TEMPLATE.md)

## Code of Conduct

We adhere to the [Code of Conduct](https://github.com/qqAys/StarDrive/blob/main/CODE_OF_CONDUCT.md) to ensure all participants in StarDrive feel welcome and safe.

By participating in discussions and contributions, you agree to abide by its terms.

## Contributing Code

### Environment Setup

To set up your local development environment for StarDrive, you need to install Python 3.12+ and [uv](https://docs.astral.sh/uv/).

You can install `uv` using the following commands:

macOS/Linux:
```shell
curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh
```

Windows:
```shell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Once `uv` is installed, you can install StarDrive's dependencies with this command:

```shell
uv sync
```

### Coding Style

StarDrive uses [Black](https://github.com/psf/black) for code formatting.


You can format your code using the following command:

```shell
uv run black .
```

### Testing

StarDrive uses [pytest](https://docs.pytest.org/en/latest/) for writing and running tests.

Please ensure all tests pass before submitting a pull request. To run all tests from the root directory of StarDrive, use this command:

```shell
uv run pytest
```

### Translations

1. This project uses `pybabel` to create the translation file `.pot`:

    ```shell
    uv run pybabel extract -F babel.cfg -o locales/messages.pot .
    ```

2. After initializing the `.pot` file, create the language file for the language you want to translate:

    ```shell
    uv run pybabel init -i locales/messages.pot -d locales -l {your_language_code}
    ```

3. Open the `.po` file with your favorite editor and fill in the translation in the `msgstr` field.

4. Generate the compiled language file `.mo` for testing:

    ```shell
    uv run pybabel compile -d locales
    ```

5. After successful testing, commit the `locales/{your_language_code}/LC_MESSAGES/messages.po` file to version control. Please note the `.gitignore` file and do not commit the `.pot` or `.mo` files.


### Creating a Pull Request (PR)

When creating a pull request, please ensure you follow these steps:

1. Create a fork of the repository and clone it to your local machine.

2. Create a feature branch based on `main` (the primary branch of your fork). (e.g., `feat/my-new-feature`, `fix/bug-description`, `docs/update-readme`).

3. Add your changes and commit them.

4. Format your code and run the tests.

5. Push your changes to your fork.

6. Create a pull request, following the [Pull Request Template](https://github.com/qqAys/StarDrive/blob/main/.github/PULL_REQUEST_TEMPLATE.md), provide a detailed description of your changes, and wait for us to review and merge.

When submitting a pull request, please ensure the code adheres to the existing coding style and that all tests pass. If you are adding a new feature, please include tests that cover the new functionality.

## Acknowledgments

A sincere thank you to all the contributors who have helped make StarDrive better!
