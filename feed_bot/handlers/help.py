from asyncio import sleep

from telethon.events import NewMessage, StopPropagation

from .base import BaseFeedBotHandler
from common.persistent_storage.base import IPersistentStorage
from common.logging import get_logger
from common.resources.localization import get_localized, g_key_handlers_help_0, g_key_handlers_help_1
from common.resources.localization import g_key_handlers_help_2


class HelpHandler(BaseFeedBotHandler):
    def __init__(self, persistent_storage: IPersistentStorage):
        super(HelpHandler, self).__init__(persistent_storage=persistent_storage)

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        get_logger().info(msg=f"help handler called, chat_id={event.chat_id}")
        # assert user is enrolled
        locale = await self.assert_enrolled(event=event)

        keys = [g_key_handlers_help_0, g_key_handlers_help_1, g_key_handlers_help_2]

        for idx, key in enumerate(keys):
            is_last = idx == len(keys)
            await event.message.respond(get_localized(key, locale), parse_mode="md")

            if not is_last:
                await sleep(1)

        raise StopPropagation
