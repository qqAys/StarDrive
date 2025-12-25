from typing import Optional, Union

from nicegui import ui
from nicegui.elements.mixins.validation_element import (
    ValidationFunction,
    ValidationDict,
)
from nicegui.events import Handler, ValueChangeEventArguments


class Input(ui.input):
    """
    An enhanced input field that supports an appended icon on the right side.

    This component extends NiceGUI's standard input with a consistent way to display
    an icon (e.g., for visual hints or actions) while preserving all original functionality
    such as validation, password masking, autocomplete, and event handling.
    """

    def __init__(
        self,
        label: Optional[str] = None,
        icon: Optional[str] = None,
        *,
        placeholder: Optional[str] = None,
        value: str = "",
        password: bool = False,
        password_toggle_button: bool = False,
        on_change: Optional[Handler[ValueChangeEventArguments]] = None,
        autocomplete: Optional[list[str]] = None,
        validation: Optional[Union[ValidationFunction, ValidationDict]] = None,
    ):
        super().__init__(
            label=label,
            placeholder=placeholder,
            value=value,
            password=password,
            password_toggle_button=password_toggle_button,
            on_change=on_change,
            autocomplete=autocomplete,
            validation=validation,
        )
        # Append an icon to the right side of the input if specified
        if icon:
            with self.add_slot("append"):
                ui.icon(icon)


input_with_icon = Input
