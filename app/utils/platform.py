from nicegui import ui, app

MAC_KEYMAP = {
    "Control": "⌃",
    "Command": "⌘",
    "Cmd": "⌘",
    "Option": "⌥",
    "Alt": "⌥",
    "Shift": "⇧",
    "Enter": "⏎",
    "Backspace": "⌫",
    "Space": "␣",
    "Up": "↑",
    "Down": "↓",
}

WIN_KEYMAP = {
    "Control": "Ctrl",
    "Command": "Ctrl",
    "Cmd": "Ctrl",
    "Option": "Alt",
    "Alt": "Alt",
    "Shift": MAC_KEYMAP["Shift"],
    "Enter": MAC_KEYMAP["Enter"],
    "Backspace": MAC_KEYMAP["Backspace"],
    "Space": MAC_KEYMAP["Space"],
    "Up": MAC_KEYMAP["Up"],
    "Down": MAC_KEYMAP["Down"],
}


def normalize_key(key: str) -> str:
    is_mac = app.storage.user.get("is_mac", False)
    if is_mac:
        return MAC_KEYMAP.get(key, key)
    return WIN_KEYMAP.get(key, key)


async def detect_platform():
    return await ui.run_javascript(
        """
        return {
            is_mac: navigator.platform.includes("Mac"),
            platform: navigator.platform,
            user_agent: navigator.userAgent,
        }
        """
    )
