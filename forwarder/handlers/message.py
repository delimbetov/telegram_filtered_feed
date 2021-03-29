from telethon.events import NewMessage, StopPropagation

from common.handler import CallableHandlerWithStorage
from common.logging import get_logger
from common.telegram import get_chat_type_from_event, ChatType, get_forwarded_message_hash
from common.persistent_storage.base import IPersistentStorage
from common.protocol import MessageType


class MessageHandler(CallableHandlerWithStorage):
    def __init__(self, persistent_storage: IPersistentStorage, feedbot_entity):
        super(MessageHandler, self).__init__(persistent_storage=persistent_storage)
        self.feedbot_entity = feedbot_entity

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        if event.message.grouped_id is not None:
            get_logger().debug(
                msg=f"message handler called, chat_id={event.chat_id} msg id={event.message.id}; skip because album")
            raise StopPropagation

        get_logger().info(msg=f"message handler called, chat_id={event.chat_id} msg id={event.message.id}")
        if get_chat_type_from_event(event=event) != ChatType.CHANNEL:
            get_logger().warning(msg=f"chat id={event.chat_id} is not a channel so do nothing: {event}")
            raise StopPropagation

        # forward
        chat = await event.get_chat()

        if chat.username is None:
            # private channels path
            # forward message
            forwarded_message = await event.client.forward_messages(
                entity=self.feedbot_entity,
                as_album=False,
                messages=event.message)

            # send source channel info
            await event.client.send_message(
                entity=self.feedbot_entity,
                message=f"{MessageType.FORWARD_SOURCE.name} {event.chat_id} "
                        f"{get_forwarded_message_hash(forwarded_message)}")
        else:
            # public channels path
            # no need for export link - just send username (because id wont be resolved) and msg_id.
            # it WORKS with not joined channels (public)
            await event.client.send_message(
                entity=self.feedbot_entity,
                message=f"{MessageType.MESSAGE.name} {chat.username} {event.message.id}")

        raise StopPropagation
