from telethon.events import NewMessage, StopPropagation
from .base import BaseFeedBotHandler
from common.persistent_storage.base import IPersistentStorage
from common.logging import get_logger

from common.resources.localization import get_localized, g_key_handlers_stop_not_started, g_key_handlers_stop_did_stop


class StopHandler(BaseFeedBotHandler):
    def __init__(self, persistent_storage: IPersistentStorage):
        super(StopHandler, self).__init__(persistent_storage=persistent_storage)

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        get_logger().info(msg=f"stop handler called, chat_id={event.chat_id}")
        # assert user is enrolled
        locale = await self.assert_enrolled(event=event)

        # disable chat
        enabled_before = await self.persistent_storage.disable_user_chat(chat_id=event.chat_id)

        # if it was enabled, its disabled now; else tell user its already disabled
        if enabled_before:
            get_logger().info(f"user_chat_id={event.chat_id} disabled")
            await event.message.respond(get_localized(g_key_handlers_stop_did_stop, locale))
        else:
            # should not be here unless user spams with stop/start
            get_logger().info(f"user_chat_id={event.chat_id} already disabled - should not happen unless user spams")
            await event.message.respond(get_localized(g_key_handlers_stop_not_started, locale))

        raise StopPropagation
