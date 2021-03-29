from abc import ABC, abstractmethod
from common.telegram import ChatType
from common.resources.localization import Language
from common.interval import MultiInterval


# Must be thread safe
class IPersistentStorage(ABC):
    # special methods to handle async with
    @abstractmethod
    async def __aenter__(self):
        pass

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    # subscription to notifies; notifies_to_handlers is notify: str to handler: coroutine
    # NOTE: subscribe and listen should get the same connection to work
    @abstractmethod
    async def subscribe(self, notifies_to_handlers: dict):
        pass

    @abstractmethod
    async def listen(self, notifies_to_handlers: dict, should_run_func):
        pass

    # User subs ops
    # returns is_enrolled: bool, locale: Language
    @abstractmethod
    async def get_user_enrolled_and_locale(self, user_chat_id: int) -> tuple:
        pass

    @abstractmethod
    async def get_user_chat_id_enabled_subscriptions(self, user_chat_id: int) -> list:
        pass

    # returns existed_before, enabled_before
    @abstractmethod
    async def add_or_enable_user_chat(self, chat_id: int, chat_type: ChatType, language: Language) -> tuple:
        pass

    @abstractmethod
    async def disable_user_chat(self, chat_id: int) -> bool:
        pass

    @abstractmethod
    async def add_or_enable_subscription(
            self, user_chat_id: int, target_chat_id: int, target_title: str, target_joiner: str) -> tuple:
        pass

    @abstractmethod
    async def get_all_user_chats(self) -> set:
        pass

    # returns enabled_before, did_disable
    @abstractmethod
    async def disable_subscription(self, user_chat_id: int, target_chat_id: int) -> tuple:
        pass

    # Channel subs ops
    @abstractmethod
    async def get_channel_subscribers(self, chat_id) -> set:
        pass

    @abstractmethod
    async def get_monitored_channels_delta(
            self, handicap_seconds: int, prev_max_time: str, monitored_chats_id_interval: MultiInterval) -> tuple:
        pass
