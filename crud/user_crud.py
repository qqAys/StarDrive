from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.user_model import User, Role, UserRoleLink
from security.hashing import HashingManager


class UserCRUD:

    # 创建
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        email: str,
        password: str,
        is_superuser: bool = False,
    ) -> User:
        user = User(
            email=email,
            password_hash=HashingManager.hash_password(password),
            is_superuser=is_superuser,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    # 读取
    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        user_id: str,
    ) -> Optional[User]:
        return await session.get(User, user_id)

    @staticmethod
    async def get_by_email(
        session: AsyncSession,
        email: str,
    ) -> Optional[User]:
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
        stmt = select(User).offset(offset).limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    # 更新
    @staticmethod
    async def update_password(
        session: AsyncSession,
        *,
        user: User,
        new_password: str,
        revoke_tokens: bool = True,
    ) -> User:
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
        user.is_active = is_active
        session.add(user)
        await session.commit()
        return user

    # 删除
    @staticmethod
    async def delete(
        session: AsyncSession,
        *,
        user: User,
    ) -> None:
        await session.delete(user)
        await session.commit()

    # 授权
    @staticmethod
    async def authenticate(
        session: AsyncSession,
        *,
        email: str,
        password: str,
    ) -> Optional[User]:
        user = await UserCRUD.get_by_email(session, email)
        if not user or not user.is_active:
            return None
        if not HashingManager.verify_password(password, user.password_hash):
            return None
        return user

    # 权限绑定
    @staticmethod
    async def add_role(
        session: AsyncSession,
        *,
        user: User,
        role: Role,
    ) -> None:
        stmt = select(UserRoleLink).where(
            UserRoleLink.user_id == user.id,
            UserRoleLink.role_id == role.id,
        )
        result = await session.execute(stmt)
        if result.scalar():
            return

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
        stmt = select(UserRoleLink).where(
            UserRoleLink.user_id == user.id,
            UserRoleLink.role_id == role.id,
        )
        result = await session.execute(stmt)
        link = result.scalar()
        if link:
            await session.delete(link)
            await session.commit()
