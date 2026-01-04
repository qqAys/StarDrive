from abc import ABC, abstractmethod


class Theme(ABC):
    """UI Theme Design"""

    @property
    @abstractmethod
    def primary(self) -> str: ...

    @property
    @abstractmethod
    def secondary(self) -> str: ...

    @property
    @abstractmethod
    def accent(self) -> str: ...

    @property
    @abstractmethod
    def background(self) -> str: ...

    @property
    @abstractmethod
    def dark(self) -> str: ...

    @property
    @abstractmethod
    def dark_background(self) -> str: ...

    @property
    @abstractmethod
    def positive(self) -> str: ...

    @property
    @abstractmethod
    def negative(self) -> str: ...

    @property
    @abstractmethod
    def warning(self) -> str: ...

    @property
    @abstractmethod
    def info(self) -> str: ...

    # ========= Text =========
    @property
    @abstractmethod
    def text_primary(self) -> str: ...

    @property
    @abstractmethod
    def text_secondary(self) -> str: ...

    @property
    @abstractmethod
    def text_muted(self) -> str: ...

    @property
    @abstractmethod
    def text_inverted(self) -> str: ...
