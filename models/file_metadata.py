from typing import Literal, Optional


class FileMetadata:
    """
    文件系统元数据的基类 (Base class for file system metadata).
    """

    def __init__(
        self,
        name: str,
        path: str,
        type_: Literal["file", "dir", "link"],
        size: int = 0,
        created_at: Optional[float] = None,
        num_children: int = 0,
    ):
        self.name: str = name
        self.path: str = path
        self.type: Literal["file", "dir", "link"] = type_
        self.size: int = size
        self.created_at: Optional[float] = created_at
        self.num_children: int = num_children

    def __repr__(self) -> str:
        """可读表示"""
        return (
            f"{self.__class__.__name__}(name='{self.name}', "
            f"path='{self.path}', type='{self.type}', "
            f"size={self.size}, created_at={self.created_at}), "
            f"num_children={self.num_children})"
        )


class Symlink(FileMetadata):
    """
    表示符号链接的类 (Represents a symbolic link).
    """

    def __init__(
        self,
        name: str,
        path: str,
        # 目标路径
        target_path: str,
        size: int = 0,
        created_at: Optional[float] = None,
    ):
        super().__init__(
            name=name, path=path, type_="link", size=size, created_at=created_at
        )
        self.target_path: str = target_path

    def __repr__(self) -> str:
        """目标路径信息"""
        base_repr = super().__repr__().rstrip(")")
        return f"{base_repr}, target_path='{self.target_path}')"
