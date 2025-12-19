import fnmatch

UNRESTRICTED_PAGE_ROUTES = (
    "/*.ico",
    "/*.png",
    "/*.webmanifest",
    "/apple-touch-icon*",
    "/login*",
    "/share*",
)


def is_route_unrestricted(route: str) -> bool:
    return any(fnmatch.fnmatch(route, pattern) for pattern in UNRESTRICTED_PAGE_ROUTES)
