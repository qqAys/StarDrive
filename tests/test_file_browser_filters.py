import pytest

from app.schemas.file_schema import DirMetadata, FileMetadata, FileType
from app.ui.components.browser_filters import matches_entry


@pytest.mark.parametrize("prefix", ["local/docs", "oss-prefix/users/sample/docs"])
@pytest.mark.parametrize("kind", ["all", "file", "dir", FileType.FILE, FileType.DIR])
def test_filter_metadata_types_and_names(prefix, kind):
    entries = [
        FileMetadata(name="Report.TXT", path=f"{prefix}/Report.TXT"),
        DirMetadata(name="Reports", path=f"{prefix}/Reports"),
        FileMetadata(name="other.txt", path=f"{prefix}/other.txt"),
    ]
    result = [
        item for item in entries if matches_entry(item.name, item.type, "REPORT", kind)
    ]
    assert result == [
        item for item in entries[:2] if kind == "all" or item.type == kind
    ]


@pytest.mark.parametrize("kind", ["all", "file", "dir"])
def test_no_matching_name(kind):
    assert not matches_entry("example", FileType.FILE, "missing", kind)


def test_matching_is_literal_and_supports_enum_and_string():
    assert matches_entry("a[1]%.txt", "file", "[1]%", FileType.FILE)
    assert matches_entry("中文资料", FileType.DIR, "资料", "dir")
    assert not matches_entry("example", FileType.FILE, entry_filter="dir")
