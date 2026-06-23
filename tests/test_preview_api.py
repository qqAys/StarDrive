from app.api.preview import (
    build_libreoffice_installation_page,
    find_libreoffice_command,
)


def test_libreoffice_installation_page_has_server_installation_guidance():
    page = build_libreoffice_installation_page()

    assert "Office 预览暂不可用" in page
    assert "服务器环境缺少组件" in page
    assert "brew install --cask libreoffice" in page
    assert "sudo apt install -y libreoffice libreoffice-calc" in page
    assert "重新构建并部署镜像" in page


def test_find_libreoffice_command_checks_macos_app_bundle(monkeypatch, tmp_path):
    import app.api.preview as preview

    app_binary = tmp_path / "LibreOffice.app" / "Contents" / "MacOS" / "soffice"
    app_binary.parent.mkdir(parents=True)
    app_binary.touch()
    monkeypatch.setattr(preview.shutil, "which", lambda _command: None)
    monkeypatch.setattr(preview, "Path", lambda _path: app_binary)

    assert find_libreoffice_command() == app_binary.as_posix()
