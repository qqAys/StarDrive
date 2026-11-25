"""Pure predicates for already loaded current-directory metadata."""

from math import isfinite

from app.schemas.file_schema import FileType


def matches_entry(
    name: str,
    entry_type: FileType | str,
    query: str = "",
    entry_filter: FileType | str = "all",
    size: int | None = None,
    minimum: float | None = None,
    maximum: float | None = None,
) -> bool:
    if minimum is not None or maximum is not None:
        if entry_type != FileType.FILE or size is None:
            return False
        if minimum is not None and size < minimum:
            return False
        if maximum is not None and size > maximum:
            return False
    return query.casefold() in name.casefold() and (
        entry_filter == "all" or entry_type == entry_filter
    )


def parse_size_range(minimum, maximum) -> tuple[float | None, float | None]:
    """Validate optional MiB bounds and convert them to bytes."""
    bounds = []
    for value in (minimum, maximum):
        if value is None or str(value).strip() == "":
            bounds.append(None)
            continue
        try:
            size = float(value) * 1024**2
        except (ValueError, TypeError, OverflowError):
            raise ValueError("invalid_size") from None
        if not isfinite(size) or size < 0:
            raise ValueError("invalid_size")
        bounds.append(size)
    lower, upper = bounds
    if lower is not None and upper is not None and lower > upper:
        raise ValueError("reversed_range")
    return lower, upper
