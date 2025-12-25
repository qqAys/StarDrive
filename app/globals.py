from typing import Optional

from app.services.file_service import StorageManager
from app.services.user_service import UserManager

storage_manager_instance: Optional[StorageManager] = None
user_manager_instance: Optional[UserManager] = None


def get_storage_manager() -> StorageManager:
    """
    Retrieve the singleton instance of StorageManager.

    Raises:
        RuntimeError: If the StorageManager has not been initialized during application startup.
    """
    if storage_manager_instance is None:
        raise RuntimeError(
            "StorageManager is not initialized. Please ensure it is set during application startup."
        )
    return storage_manager_instance


def get_user_manager() -> UserManager:
    """
    Retrieve the singleton instance of UserManager.

    Raises:
        RuntimeError: If the UserManager has not been initialized during application startup.
    """
    if user_manager_instance is None:
        raise RuntimeError(
            "UserManager is not initialized. Please ensure it is set during application startup."
        )
    return user_manager_instance


def set_storage_manager(manager: StorageManager):
    """
    Set the global StorageManager instance.

    This function should be called once during application startup.
    """
    global storage_manager_instance
    storage_manager_instance = manager


def set_user_manager(manager: UserManager):
    """
    Set the global UserManager instance.

    This function should be called once during application startup.
    """
    global user_manager_instance
    user_manager_instance = manager
