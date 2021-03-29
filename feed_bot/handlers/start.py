from asyncio import sleep

from telethon.events import NewMessage, StopPropagation
from telethon.tl.types import User
from .base import BaseFeedBotHandler, get_sender_and_language_from_event
from common.persistent_storage.base import IPersistentStorage
from common.logging import get_logger
from common.telegram import get_chat_type_from_event

from common.resources.localization import get_localized, g_key_handlers_start_already_enabled
from common.resources.localization import g_key_handlers_start_already_existed, g_key_handlers_start_introduction_0
from common.resources.localization import g_key_handlers_start_introduction_1, g_key_handlers_start_introduction_2
from common.resources.localization import g_key_handlers_start_not_user


class StartHandler(BaseFeedBotHandler):
    def __init__(self, persistent_storage: IPersistentStorage):
        super(StartHandler, self).__init__(persistent_storage=persistent_storage)

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        chat_id = event.chat_id
        chat_type = get_chat_type_from_event(event=event)
        sender, language = await get_sender_and_language_from_event(event)

        if not isinstance(sender, User):
            get_logger().debug(f"Start command not from user received: chat_id={chat_id}")
            await event.message.respond(get_localized(g_key_handlers_start_not_user, language))
            raise StopPropagation

        get_logger().info(msg=f"start handler called; user_name={sender.username} chat_id={chat_id} "
                              f"chat_type={chat_type.name} language={language.name}")

        # check if chat were stored/enabled already, on lack of it add
        existed_before, enabled_before, db_language = await self.persistent_storage.add_or_enable_user_chat(
            chat_id=chat_id, chat_type=chat_type, language=language)
        get_logger().debug(f"chat_id={chat_id} existed_before={existed_before}, enabled_before={enabled_before}, "
                           f"db_language={db_language}")

        if enabled_before:
            await event.message.respond(get_localized(g_key_handlers_start_already_enabled, db_language))
        elif existed_before:
            await event.message.respond(get_localized(g_key_handlers_start_already_existed, db_language))
        else:
            # new user - send introduction
            # sleep between parts of the introduction so user will notice
            await event.message.respond(get_localized(g_key_handlers_start_introduction_0, db_language))
            await sleep(3)
            await event.message.respond(get_localized(g_key_handlers_start_introduction_1, db_language))
            await sleep(3)
            await event.message.respond(get_localized(g_key_handlers_start_introduction_2, db_language))

        raise StopPropagation
