"""Exercise callbacks built by the real console renderer, without a browser.

The UI transport alone is replaced. These are not browser/keyboard/viewport tests.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.security import guards
from app.ui.pages import console


class Dialog(MagicMock):
    def __await__(self):
        return self.result.__await__()


def render_harness(monkeypatch):
    elements = []

    def element(kind, *args, **kwargs):
        item = Dialog() if kind == "dialog" else MagicMock()
        item.kind = kind
        # NiceGUI select takes options positionally and its label by keyword.
        item.label = kwargs.get("label", args[0] if args else None)
        item.value = kwargs.get("value")
        item.callback = kwargs.get("on_click")
        item.handlers = {}
        item.__enter__.return_value = item
        item.classes.return_value = item
        item.props.return_value = item
        item.on.side_effect = lambda event, handler: item.handlers.update(
            {event: handler}
        )
        if kind == "dialog":
            item.result = asyncio.get_running_loop().create_future()
            item.submit.side_effect = lambda value: item.result.set_result(value)
        elements.append(item)
        return item

    ui = SimpleNamespace(
        **{
            kind: (lambda *args, _kind=kind, **kwargs: element(_kind, *args, **kwargs))
            for kind in (
                "label",
                "row",
                "column",
                "grid",
                "card",
                "dialog",
                "input",
                "select",
                "button",
                "table",
                "list",
                "item",
                "expansion",
            )
        }
    )
    monkeypatch.setattr(console, "ui", ui)
    monkeypatch.setattr(console, "_", lambda value: value)
    monkeypatch.setattr(console, "notify", MagicMock())
    monkeypatch.setattr(guards, "notify", MagicMock())
    monkeypatch.setattr(guards, "navigate_to", MagicMock())
    monkeypatch.setattr(
        guards, "app", SimpleNamespace(storage=SimpleNamespace(user={"id": "admin"}))
    )
    user = SimpleNamespace(is_active=True, is_superuser=True)
    monkeypatch.setattr(
        guards.globals,
        "get_user_manager",
        lambda: SimpleNamespace(current_user=AsyncMock(return_value=user)),
    )
    service = SimpleNamespace(
        list_profiles=AsyncMock(return_value=[]),
        create_or_update_profile=AsyncMock(),
        test_profile=AsyncMock(
            return_value=SimpleNamespace(success=True, message="verified")
        ),
        activate_profile=AsyncMock(),
        delete_profile=AsyncMock(),
    )
    monkeypatch.setattr(console, "storage_config", service)

    def find(kind, label=None):
        return next(
            item
            for item in reversed(elements)
            if item.kind == kind and (label is None or item.label == label)
        )

    return find, service, user, elements


def test_console_editor_save_and_test_use_real_draft_callbacks(monkeypatch):
    async def scenario():
        find, service, user, elements = render_harness(monkeypatch)
        await console._render_storage_section()
        editor = asyncio.create_task(find("button", "New profile").callback())
        await asyncio.sleep(0)
        find("input", "Profile name").value = "Synthetic S3"
        backend = find("select", "Backend type")
        backend.value = console.S3
        backend.handlers["update:model-value"](None)
        assert find(
            "label",
            "S3 tests write and delete a unique object under .stardrive-probes. "
            "Private HTTP/HTTPS endpoints are allowed; use only trusted destinations.",
        ).visible
        for label, value in {
            "Endpoint": "http://127.0.0.1:9000",
            "Region": "test",
            "Bucket": "synthetic",
            "Object prefix": "root",
            "AccessKey ID": "synthetic-id",
            "AccessKey Secret": "synthetic-secret",
        }.items():
            find("input", label).value = value
        await find("button", "Test draft").callback()
        draft = service.test_profile.call_args.kwargs["draft_config"]
        assert draft.backend_type == console.S3
        assert draft.secrets == {
            "access_key_id": "synthetic-id",
            "access_key_secret": "synthetic-secret",
        }
        assert draft.public_config["endpoint"] == "http://127.0.0.1:9000"
        await find("button", "Save profile").callback()
        await editor
        saved = service.create_or_update_profile.call_args.args[0]
        assert saved == draft
        assert service.list_profiles.await_count == 2

    asyncio.run(scenario())


@pytest.mark.parametrize("state", ["ordinary", "revoked", "disabled"])
def test_actual_saved_profile_callbacks_recheck_permissions(monkeypatch, state):
    async def scenario():
        find, service, user, elements = render_harness(monkeypatch)
        await console._render_storage_section()
        row = dict(
            id="s3",
            name="Synthetic",
            backend=console.S3,
            backend_type=console.S3,
            active="No",
            is_active=False,
            secrets="Yes",
            tested="-",
            result="-",
            last_test_message="-",
            public_config={},
        )
        info = asyncio.create_task(
            find("table").handlers["info"](SimpleNamespace(args=row))
        )
        await asyncio.sleep(0)
        profile_dialog = find("dialog")
        # Permission is changed after the renderer and information dialog exist.
        if state in {"ordinary", "revoked"}:
            user.is_superuser = False
        else:
            user.is_active = False
        await find("button", "Test").callback()
        await info
        service.test_profile.assert_not_awaited()
        # Retained callback references must also refuse activate/delete/edit.
        for label in ("Activate", "Delete", "Edit"):
            callback = find("button", label).callback
            # These wrappers also submit the dialog; preserve a fresh transport future.
            profile_dialog.result = asyncio.get_running_loop().create_future()
            await callback()
        service.activate_profile.assert_not_awaited()
        service.delete_profile.assert_not_awaited()
        service.create_or_update_profile.assert_not_awaited()
        assert len([item for item in elements if item.kind == "dialog"]) == 1
        assert guards.notify.error.call_count == 4

    asyncio.run(scenario())


@pytest.mark.parametrize("revoke", [False, True])
def test_actual_activate_callback_rechecks_after_confirmation(monkeypatch, revoke):
    async def scenario():
        find, service, user, elements = render_harness(monkeypatch)
        await console._render_storage_section()
        row = dict(
            id="s3",
            name="Synthetic",
            backend=console.S3,
            backend_type=console.S3,
            active="No",
            is_active=False,
            secrets="Yes",
            tested="-",
            result="-",
            last_test_message="-",
            public_config={},
        )
        info = asyncio.create_task(
            find("table").handlers["info"](SimpleNamespace(args=row))
        )
        await asyncio.sleep(0)
        entered, release = asyncio.Event(), asyncio.Event()

        async def confirm():
            entered.set()
            await release.wait()
            return True

        monkeypatch.setattr(
            console,
            "ConfirmDialog",
            lambda *args, **kwargs: SimpleNamespace(open=confirm),
        )
        activation = asyncio.create_task(find("button", "Activate").callback())
        await entered.wait()
        user.is_superuser = not revoke
        release.set()
        await activation
        await info
        if revoke:
            service.activate_profile.assert_not_awaited()
            assert guards.notify.error.call_count == 1
        else:
            service.activate_profile.assert_awaited_once_with("s3")
            assert service.list_profiles.await_count == 2
            guards.notify.error.assert_not_called()

    asyncio.run(scenario())
