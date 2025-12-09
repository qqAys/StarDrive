from typing import Optional

from storage.manager import StorageManager

storage_manager_instance: Optional[StorageManager] = None


def get_storage_manager() -> StorageManager:
    """
    获取 StorageManager 实例。
    """
    if storage_manager_instance is None:
        raise RuntimeError(
            "StorageManager is not initialized. Please make sure to set it in app startup."
        )
    return storage_manager_instance


def set_storage_manager(manager: StorageManager):
    global storage_manager_instance
    storage_manager_instance = manager
