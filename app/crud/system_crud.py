from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.system_model import AppSetting, StorageProfile


class AppSettingCRUD:
    @staticmethod
    async def get(session: AsyncSession, key: str) -> AppSetting | None:
        return await session.get(AppSetting, key)

    @staticmethod
    async def get_value(
        session: AsyncSession, key: str, default: str | None = None
    ) -> str | None:
        setting = await AppSettingCRUD.get(session, key)
        return setting.value if setting else default

    @staticmethod
    async def set_value(session: AsyncSession, key: str, value: str) -> AppSetting:
        setting = await AppSettingCRUD.get(session, key)
        if setting:
            setting.value = value
        else:
            setting = AppSetting(key=key, value=value)
        session.add(setting)
        await session.commit()
        await session.refresh(setting)
        return setting


class StorageProfileCRUD:
    @staticmethod
    async def list(session: AsyncSession) -> list[StorageProfile]:
        result = await session.execute(
            select(StorageProfile).order_by(
                StorageProfile.is_active.desc(),
                StorageProfile.created_at.asc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get(session: AsyncSession, profile_id: str) -> StorageProfile | None:
        return await session.get(StorageProfile, profile_id)

    @staticmethod
    async def get_active(session: AsyncSession) -> StorageProfile | None:
        result = await session.execute(
            select(StorageProfile).where(StorageProfile.is_active.is_(True))
        )
        return result.scalar()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        name: str,
        backend_type: str,
        public_config: dict,
        encrypted_secrets: dict | None = None,
        is_active: bool = False,
    ) -> StorageProfile:
        profile = StorageProfile(
            name=name,
            backend_type=backend_type,
            public_config=public_config,
            encrypted_secrets=encrypted_secrets or {},
            is_active=is_active,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile

    @staticmethod
    async def update(
        session: AsyncSession,
        profile: StorageProfile,
        *,
        name: str,
        public_config: dict,
        encrypted_secrets: dict,
    ) -> StorageProfile:
        profile.name = name
        profile.public_config = public_config
        profile.encrypted_secrets = encrypted_secrets
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile

    @staticmethod
    async def activate(session: AsyncSession, profile: StorageProfile) -> None:
        result = await session.execute(select(StorageProfile))
        for existing in result.scalars().all():
            existing.is_active = existing.id == profile.id
            session.add(existing)
        await session.commit()

    @staticmethod
    async def delete(session: AsyncSession, profile: StorageProfile) -> None:
        await session.delete(profile)
        await session.commit()

    @staticmethod
    async def record_test_result(
        session: AsyncSession,
        profile: StorageProfile,
        *,
        tested_at,
        success: bool,
        message: str,
    ) -> StorageProfile:
        profile.last_tested_at = tested_at
        profile.last_test_success = success
        profile.last_test_message = message[:512]
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile
