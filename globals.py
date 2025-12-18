from typing import Optional

from services.file_service import StorageManager
from services.user_service import UserManager

storage_manager_instance: Optional[StorageManager] = None
user_manager_instance: Optional[UserManager] = None


def get_storage_manager() -> StorageManager:
    """
    获取 StorageManager 实例。
    """
    if storage_manager_instance is None:
        raise RuntimeError(
            "StorageManager is not initialized. Please make sure to set it in app startup."
        )
    return storage_manager_instance


def get_user_manager() -> UserManager:
    if user_manager_instance is None:
        raise RuntimeError(
            "UserManager is not initialized. Please make sure to set it in app startup."
        )
    return user_manager_instance


def set_storage_manager(manager: StorageManager):
    global storage_manager_instance
    storage_manager_instance = manager


def set_user_manager(manager: UserManager):
    global user_manager_instance
    user_manager_instance = manager
