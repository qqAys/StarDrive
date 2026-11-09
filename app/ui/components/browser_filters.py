"""Pure predicates for already loaded current-directory metadata."""

from app.schemas.file_schema import FileType


def matches_entry(
    name: str,
    entry_type: FileType | str,
    query: str = "",
    entry_filter: FileType | str = "all",
) -> bool:
    return query.casefold() in name.casefold() and (
        entry_filter == "all" or entry_type == entry_filter
    )
