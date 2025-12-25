from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.user_model import User, Role, UserRoleLink
from app.security.hashing import HashingManager


class UserCRUD:
    """
    Data Access Layer for User-related operations.
    Provides methods to create, read, update, delete, authenticate users,
    and manage role assignments.
    """

    # Create
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        email: str,
        password: str,
        is_superuser: bool = False,
    ) -> User:
        """
        Create a new user with the provided email and password.

        Args:
            session: The async database session.
            email: The user's email address.
            password: The plain-text password to be hashed and stored.
            is_superuser: Whether the user should have superuser privileges.

        Returns:
            The newly created User instance.
        """
        user = User(
            email=email,
            password_hash=HashingManager.hash_password(password),
            is_superuser=is_superuser,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    # Read
    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        user_id: str,
    ) -> Optional[User]:
        """
        Retrieve a user by their unique ID.

        Args:
            session: The async database session.
            user_id: The unique identifier of the user.

        Returns:
            The User instance if found; otherwise, None.
        """
        return await session.get(User, user_id)

    @staticmethod
    async def get_by_email(
        session: AsyncSession,
        email: str,
    ) -> Optional[User]:
        """
        Retrieve a user by their email address.

        Args:
            session: The async database session.
            email: The email address of the user.

        Returns:
            The User instance if found; otherwise, None.
        """
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        return result.scalar()

    @staticmethod
    async def list(
        session: AsyncSession,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[User]:
        """
        Retrieve a paginated list of users.

        Args:
            session: The async database session.
            offset: Number of records to skip (for pagination).
            limit: Maximum number of records to return.

        Returns:
            A sequence of User instances.
        """
        stmt = select(User).offset(offset).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    # Update
    @staticmethod
    async def update_password(
        session: AsyncSession,
        *,
        user: User,
        new_password: str,
        revoke_tokens: bool = True,
    ) -> User:
        """
        Update a user's password and optionally invalidate existing tokens.

        Args:
            session: The async database session.
            user: The User instance to update.
            new_password: The new plain-text password.
            revoke_tokens: If True, increments token_version to invalidate active sessions.

        Returns:
            The updated User instance.
        """
        user.password_hash = HashingManager.hash_password(new_password)
        if revoke_tokens:
            user.token_version += 1

        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    @staticmethod
    async def update_status(
        session: AsyncSession,
        *,
        user: User,
        is_active: bool,
    ) -> User:
        """
        Activate or deactivate a user account.

        Args:
            session: The async database session.
            user: The User instance to update.
            is_active: Desired activation status.

        Returns:
            The updated User instance.
        """
        user.is_active = is_active
        session.add(user)
        await session.commit()
        return user

    # Delete
    @staticmethod
    async def delete(
        session: AsyncSession,
        *,
        user: User,
    ) -> None:
        """
        Permanently delete a user from the database.

        Args:
            session: The async database session.
            user: The User instance to delete.
        """
        await session.delete(user)
        await session.commit()

    # Authentication
    @staticmethod
    async def authenticate(
        session: AsyncSession,
        *,
        email: str,
        password: str,
    ) -> Optional[User]:
        """
        Authenticate a user by verifying email and password.

        Args:
            session: The async database session.
            email: The user's email address.
            password: The plain-text password provided during login.

        Returns:
            The authenticated User instance if credentials are valid and account is active;
            otherwise, None.
        """
        user = await UserCRUD.get_by_email(session, email)
        if not user or not user.is_active:
            return None
        if not HashingManager.verify_password(password, user.password_hash):
            return None
        return user

    # Role Management
    @staticmethod
    async def add_role(
        session: AsyncSession,
        *,
        user: User,
        role: Role,
    ) -> None:
        """
        Assign a role to a user if not already assigned.

        Args:
            session: The async database session.
            user: The User instance.
            role: The Role to assign.
        """
        stmt = select(UserRoleLink).where(
            UserRoleLink.user_id == user.id,
            UserRoleLink.role_id == role.id,
        )
        result = await session.execute(stmt)
        if result.scalar():
            return  # Role already assigned

        link = UserRoleLink(user_id=user.id, role_id=role.id)
        session.add(link)
        await session.commit()

    @staticmethod
    async def remove_role(
        session: AsyncSession,
        *,
        user: User,
        role: Role,
    ) -> None:
        """
        Remove a role assignment from a user.

        Args:
            session: The async database session.
            user: The User instance.
            role: The Role to remove.
        """
        stmt = select(UserRoleLink).where(
            UserRoleLink.user_id == user.id,
            UserRoleLink.role_id == role.id,
        )
        result = await session.execute(stmt)
        link = result.scalar()
        if link:
            await session.delete(link)
            await session.commit()
