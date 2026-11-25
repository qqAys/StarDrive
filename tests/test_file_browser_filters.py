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


@pytest.mark.parametrize(
    ("lower", "upper", "expected"),
    [
        (None, "", (None, None)),
        ("0", "0", (0, 0)),
        ("0.5", "1", (524288, 1048576)),
        ("1", None, (1048576, None)),
        ("", "2", (None, 2097152)),
    ],
)
def test_size_range_mib_conversion(lower, upper, expected):
    from app.ui.components.browser_filters import parse_size_range

    assert parse_size_range(lower, upper) == expected


@pytest.mark.parametrize("value", ["-1", "nan", "inf", "-inf", "1e999", "abc"])
def test_size_range_rejects_invalid_bound(value):
    from app.ui.components.browser_filters import parse_size_range

    for bounds in [(value, None), (None, value)]:
        with pytest.raises(ValueError):
            parse_size_range(*bounds)


def test_size_range_rejects_reversed_bounds():
    from app.ui.components.browser_filters import parse_size_range

    with pytest.raises(ValueError, match="reversed_range"):
        parse_size_range("2", "1")


@pytest.mark.parametrize(
    ("size", "lower", "upper", "expected"),
    [
        (0, 0, 0, True),
        (1048576, 1048576, 1048576, True),
        (1048575, 1048576, None, False),
        (1048577, None, 1048576, False),
        (0, None, 1048576, True),
    ],
)
def test_size_matching_inclusive_file_bounds(size, lower, upper, expected):
    assert (
        matches_entry("Report.txt", "file", "REPORT", "file", size, lower, upper)
        == expected
    )
    assert not matches_entry("Report", "dir", size=size, minimum=lower, maximum=upper)
    assert not matches_entry(
        "Report.txt", "file", "missing", size=size, minimum=lower, maximum=upper
    )
    assert not matches_entry(
        "Report.txt",
        "file",
        entry_filter="dir",
        size=size,
        minimum=lower,
        maximum=upper,
    )
