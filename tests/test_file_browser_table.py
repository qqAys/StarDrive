import asyncio

from app.ui.components.table import FileBrowserTable


class FakeRefreshable:
    targets = [object()]

    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.calls = 0

    async def refresh(self):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1


def test_refresh_serializes_concurrent_refreshable_calls():
    async def run_test():
        table = FileBrowserTable.__new__(FileBrowserTable)
        table.refresh_func = FakeRefreshable()
        table._refresh_lock = asyncio.Lock()

        await asyncio.gather(table.refresh(), table.refresh())

        assert table.refresh_func.calls == 2
        assert table.refresh_func.max_active == 1

    asyncio.run(run_test())
