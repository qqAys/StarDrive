"""Opt-in real OSS contract test. Never runs without dedicated test credentials."""

import asyncio
import os
from uuid import uuid4

import pytest

from app.services.storage_config_service import OSSConfig
from app.storage.aliyun_oss_storage import AliyunOSSStorage


REQUIRED = (
    "STARDRIVE_TEST_OSS_REGION",
    "STARDRIVE_TEST_OSS_ENDPOINT",
    "STARDRIVE_TEST_OSS_BUCKET",
    "STARDRIVE_TEST_OSS_ACCESS_KEY_ID",
    "STARDRIVE_TEST_OSS_ACCESS_KEY_SECRET",
    "STARDRIVE_TEST_OSS_PREFIX",
)


@pytest.mark.external
def test_aliyun_oss_upload_download_and_cleanup():
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        pytest.skip("Dedicated OSS test credentials are not configured")

    config = OSSConfig(
        region=os.environ["STARDRIVE_TEST_OSS_REGION"],
        endpoint=os.environ["STARDRIVE_TEST_OSS_ENDPOINT"],
        bucket=os.environ["STARDRIVE_TEST_OSS_BUCKET"],
        access_key_id=os.environ["STARDRIVE_TEST_OSS_ACCESS_KEY_ID"],
        access_key_secret=os.environ["STARDRIVE_TEST_OSS_ACCESS_KEY_SECRET"],
        prefix=os.environ["STARDRIVE_TEST_OSS_PREFIX"],
    )
    storage = AliyunOSSStorage(config, f"ci-{uuid4().hex}")

    async def content():
        yield b"StarDrive OSS integration test"

    asyncio.run(storage.upload_file(content(), "contract.txt"))
    try:
        assert (
            storage.download_file("contract.txt") == b"StarDrive OSS integration test"
        )
        assert storage.list_files("")[0].name == "contract.txt"
    finally:
        storage.delete_file("contract.txt")
