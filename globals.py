from typing import Optional

from storage.manager import StorageManager

storage_manager_instance: Optional[StorageManager] = None


def get_storage_manager() -> StorageManager:
    """
    获取 StorageManager 实例。
    """
    if storage_manager_instance is None:
        raise RuntimeError("StorageManager 尚未初始化。请确保在 app startup 中设置它。")
    return storage_manager_instance


def set_storage_manager(manager: StorageManager):
    global storage_manager_instance
    storage_manager_instance = manager
