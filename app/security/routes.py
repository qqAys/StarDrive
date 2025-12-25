import fnmatch

UNRESTRICTED_PAGE_ROUTES = (
    # 静态资源
    "/*.ico",
    "/*.png",
    "/*.webmanifest",
    "/apple-touch-icon*",
    # 公开路由
    "/login*",
    "/share*",
    "/api*",
)


def is_route_unrestricted(route: str) -> bool:
    return any(fnmatch.fnmatch(route, pattern) for pattern in UNRESTRICTED_PAGE_ROUTES)
