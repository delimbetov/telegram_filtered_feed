from asyncio import sleep
from math import ceil

from telethon.events import NewMessage, StopPropagation
from .base import BaseFeedBotHandler
from common.telegram import get_monitored_chat_name
from common.persistent_storage.base import IPersistentStorage
from common.logging import get_logger

from common.resources.localization import get_localized, g_key_handlers_list_count, g_key_handlers_list_list


class ListHandler(BaseFeedBotHandler):
    def __init__(self, persistent_storage: IPersistentStorage):
        super(ListHandler, self).__init__(persistent_storage=persistent_storage)

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        get_logger().info(msg=f"list handler called; chat_id={event.chat_id}")
        # assert user is enrolled
        locale = await self.assert_enrolled(event=event)
        # get channels user is subbed to
        user_chat_id_subs_title_ids = await self.persistent_storage.get_user_chat_id_enabled_subscriptions(
            user_chat_id=event.chat_id)
        sub_count = len(user_chat_id_subs_title_ids)
        get_logger().debug(msg=f"list handler: there are {sub_count} subs: {user_chat_id_subs_title_ids}")

        await event.message.respond(get_localized(g_key_handlers_list_count, locale, [sub_count]), parse_mode="md")
        if sub_count > 0:
            await sleep(0.5)

        batch_length = 5
        for idx in range(0, sub_count, batch_length):
            begin = idx
            end = min(idx + batch_length, sub_count)
            is_last = end == sub_count
            message = str()

            for title, subscription_chat_id in user_chat_id_subs_title_ids[begin: end]:
                message += "\n> "
                message += get_monitored_chat_name(title=title, chat_id=subscription_chat_id)

            # + 1 to start from 1 instead of 0
            args = [begin // batch_length + 1, ceil(sub_count / batch_length), message]
            await event.message.respond(get_localized(g_key_handlers_list_list, locale, args), parse_mode="md")
            if not is_last:
                await sleep(1)

        raise StopPropagation
