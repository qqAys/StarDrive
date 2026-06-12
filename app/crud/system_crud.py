from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_model import AppSetting


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
