请在提交拉取请求前，仔细阅读并填写以下信息。

请在对应的方框 `[]` 内填入 `x` ：

## 🚨 检查清单 (Checklist)


 - [x] 我已阅读并遵循 [行为准则](https://github.com/qqAys/StarDrive/blob/main/CODE_OF_CONDUCT.md) (Code of Conduct)

 - [x] 我已阅读并遵循 [贡献指南](https://github.com/qqAys/StarDrive/blob/main/CONTRIBUTING.md) (Contributing Guide)

 - [x] 代码已通过 `uv run black .` 格式化

 - [x] 所有现有测试均通过 (`uv run pytest`)

 - [ ] 如果是新功能，我已添加了新的测试来覆盖它

 - [ ] 如果是 UI 更改，我已附上屏幕截图

 - [ ] 如果是输出文本，我已使用 `utils` 模块的 `_` 函数进行国际化 (`_("需翻译的内容")`)

 - [ ] 如果是文档更改，我已更新了相关的文档

---

## 🌟 更改类型 (Type of Change)
本次拉取请求属于哪种类型？请选择所有适用的选项：

 - [ ] Bug 修复 (Fix)：修复了一个非破坏性的错误 (例如：`fix/login-issue`)

 - [ ] 新功能 (Feature)：添加了一个新功能或改进 (例如：`feat/add-s3-backend`)

 - [ ] 代码重构 (Refactoring)：不涉及功能或 Bug 修复的代码结构调整

 - [ ] 文档更新 (Documentation)：仅对文档（如 README、指南）进行更改

 - [ ] 样式/格式 (Style)：不影响代码运行的更改（如格式化、重命名变量）

 - [ ] 翻译 (Translation)：添加了新的翻译或更新了现有的翻译

 - [ ] 测试 (Testing)：添加或修改了测试用例

 - [ ] 依赖/环境 (Chore)：更新依赖或构建过程

---

## 📝 描述您的更改
1. **解决了什么问题？ / 动机是什么？ (What problem does this solve?)**

    请简要描述您要解决的问题或引入此更改的原因。
    （例如：修复了用户在多文件选择时，删除操作只应用到第一个文件的问题。）

2. **详细的更改内容 (Detailed changes)**

    请详细说明您在代码中做了哪些修改。如果涉及多个文件或逻辑，请分点描述。
     - 例如：在 `storage/s3.py` 中，修改了 `list_files` 方法，以正确处理 S3 分页标记。
     - 例如：在 `ui/pages/browser.py` 中，添加了新的 NiceGUI 组件来显示文件上传进度。

3. **如何测试此更改？ (How to test this change?)**

    请提供清晰的步骤，让审查者能够重现您的问题并验证您的修复或新功能。
    1. 环境准备：...（例如：需要配置一个本地 MinIO 实例） 
    2. 步骤 1：...
    3. 步骤 2：...

---

## 🖼️ 屏幕截图 / 录像 (Screenshots / Video)
如果您的更改涉及用户界面 (UI)，请在此处添加屏幕截图或 GIF 动图。

使用 Markdown 语法：

```markdown
[图片描述](图片链接)
```

---

## 🔗 相关的 Issue (Related Issue)
如果此 PR 解决了某个已存在的 Issue，请在此处引用它。使用 `closes #<issue_number>` 可以自动关闭该 Issue。

closes #<issue_number>
