# Contributing to StarDrive

We're thrilled you're interested in contributing to StarDrive!

## About the Project

StarDrive is a cloud drive system built on the [NiceGUI](https://github.com/zauberzeug/nicegui) library, featuring multi-backend storage support and comprehensive file management capabilities.

### Project Structure

* `app/` - Base directory
  * `api/` - API endpoints
  * `bootstrap/` - Initialization logic
  * `core/` - Core business logic
  * `locales/` - Translation files
  * `middlewares/` - Middleware implementations
  * `models/` - Database models
  * `schemas/` - Pydantic/Validation schemas
  * `security/` - Authentication and security logic
  * `services/` - Service layer implementations
  * `static/` - Static assets
  * `storage/ `- Storage backend drivers
  * `ui/` - Frontend components (NiceGUI)
  * `utils/` - Utility functions
  * `config.py` - Configuration management
  * `globals.py` - Global variables
  * `main.py` - Application entry point
* `tests/` - Test suite

### Tech Stack

StarDrive leverages the following technologies:

* **Python 3.12+** - Core language
* **NiceGUI**
    * **FastAPI/Starlette** - Web framework
    * **Vue 3** - Frontend framework
    * **Quasar** - UI component framework
    * **Tailwind CSS 4** - Styling
* **SQLModel** - Database ORM
* **PyJWT** - Authentication library
* **pytest** - Testing framework

## Reporting Issues

If you encounter a bug or other issues while using StarDrive, the best way to report it is by opening a new issue in our [GitHub repository](https://github.com/qqAys/StarDrive).

1.  **Bug**: Please follow the [BUG Template](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_TEMPLATE/bug_report.md)

2.  **Feature**: Please follow the [Feature Template](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_TEMPLATE/feature_request.md)

3.  **Question / Support**: Please follow the [Question Template](https://github.com/qqAys/StarDrive/blob/main/.github/ISSUE_TEMPLATE/question-or-support.md)

## Translations
StarDrive supports multiple languages. We use Weblate to manage our translations.

  * **Want to translate?** Join our project on Weblate: [https://hosted.weblate.org/projects/stardrive/](https://hosted.weblate.org/projects/stardrive/)

  * **Modified the UI?**: If your code changes include new or modified UI text, you must update the translation templates before submitting your PR (see [Updating Translation Strings](#updating-translation-strings)).

## Code of Conduct

We adhere to the [Code of Conduct](https://github.com/qqAys/StarDrive/blob/main/CODE_OF_CONDUCT.md) to ensure all participants in StarDrive feel welcome and safe.

By participating in discussions and contributions, you agree to abide by its terms.

## Contributing Code

### Environment Setup

To set up your local development environment for StarDrive, you need to install Python 3.12+ and [uv](https://docs.astral.sh/uv/).

You can install `uv` using the following commands:

```shell
# macOS/Linux:
curl -LsSf [https://astral.sh/uv/install.sh](https://astral.sh/uv/install.sh) | sh

# Windows:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Once `uv` is installed, you can install StarDrive's dependencies with this command:

```shell
uv sync
```

### Coding Style & Testing

We use **Black** for formatting and **pytest** for testing.

```shell
# Format code
uv run black .

# Run tests
uv run pytest
```

### Updating Translation Strings

If you have added or changed any translatable strings in the source code (e.g., in the `ui/` folder), 
please follow these steps to ensure the translation templates are up to date:

1. **Extract new strings** to update the `.pot` template:

    ```shell
    uv run pybabel extract -F babel.cfg -o app/locales/messages.pot .
    ```

2. **Sync the translation files** (`.po`) with the new template:

    ```shell
    uv run pybabel update -i app/locales/messages.pot -d app/locales    
    ```
      
3. **(Optional) Compile for local testing**: If you want to verify your changes locally, compile the files:

    ```
    uv run pybabel compile -d app/locales
    ```

4. **Commit the changes**: Commit the updated `app/locales/messages.pot` and the modified `.po` files.

    > Note: Do not commit the `.mo` files; they are ignored by git.

### Creating a Pull Request (PR)

1. Fork the repository and create a feature branch (e.g., `feat/new-feature` or `fix/bug-fix`).

2. Commit your changes, ensuring code is formatted and tests pass.

3. Submit your PR using our [Pull Request Template](https://github.com/qqAys/StarDrive/blob/main/.github/PULL_REQUEST_TEMPLATE.md).

## Acknowledgments

A sincere thank you to all the contributors who have helped make StarDrive better!