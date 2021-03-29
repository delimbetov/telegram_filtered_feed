from asyncio import gather

from telethon.events import NewMessage, StopPropagation
from telethon.tl.types import Message
from .base import BaseFeedBotHandler
from common.persistent_storage.base import IPersistentStorage
from common.logging import get_logger


class AllHandler(BaseFeedBotHandler):
    def __init__(self, persistent_storage: IPersistentStorage, key: str):
        super(AllHandler, self).__init__(persistent_storage=persistent_storage)
        self.key_str = key

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        get_logger().info(msg=f"all handler called; chat_id={event.chat_id}")

        # first argument is command, second must be key
        if self.key_str not in event.message.message:
            get_logger().warning(msg=f"unauthorized call of all handler!!! chat_id={event.chat_id} "
                                     f"msg={event.message.message}")
            raise StopPropagation

        # find message start
        key_pos = event.message.message.find(self.key_str)
        # act message starts from key_str end + 1 (whitespace or newline)
        actual_message = event.message.message[key_pos + len(self.key_str) + 1:]

        # get users
        users = await self.persistent_storage.get_all_user_chats()
        enabled_user_chat_ids = [chat_id for enabled, _, _, chat_id in users if enabled]
        get_logger().debug(msg=f"total users={len(users)}: {users}; "
                               f"enabled={len(enabled_user_chat_ids)}: {enabled_user_chat_ids}")
        resolved_entities = await gather(
            *[event.client.get_input_entity(chat_id) for chat_id in enabled_user_chat_ids], return_exceptions=True)

        tasks = [event.client.send_message(entity, actual_message) for entity in resolved_entities]
        sent_messages = await gather(*tasks, return_exceptions=True)
        successful_messages_count = sum(1 for msg in sent_messages if isinstance(msg, Message))
        get_logger().debug(msg=f"successful messages={successful_messages_count} out of total={sent_messages}")
        get_logger().debug(msg=f"Messages={sent_messages}")

        raise StopPropagation
