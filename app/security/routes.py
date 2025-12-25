import fnmatch

UNRESTRICTED_PAGE_ROUTES = (
    # Static assets
    "/*.ico",
    "/*.png",
    "/*.webmanifest",
    "/apple-touch-icon*",
    # Public routes
    "/login*",
    "/share*",
    "/api*",
)


def is_route_unrestricted(route: str) -> bool:
    """
    Determine whether a given route path is publicly accessible without authentication.

    This function checks if the route matches any of the predefined unrestricted patterns,
    supporting wildcards via `fnmatch`.

    Args:
        route: The full path of the incoming HTTP request (e.g., "/login", "/api/v1/files").

    Returns:
        True if the route is unrestricted; False otherwise.
    """
    return any(fnmatch.fnmatch(route, pattern) for pattern in UNRESTRICTED_PAGE_ROUTES)
