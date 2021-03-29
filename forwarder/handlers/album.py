from asyncio import sleep

from telethon.events import NewMessage, StopPropagation

from common.handler import CallableHandlerWithStorage
from common.logging import get_logger
from common.telegram import get_chat_type_from_event, ChatType, get_forwarded_message_hash
from common.persistent_storage.base import IPersistentStorage
from common.protocol import MessageType


class AlbumHandler(CallableHandlerWithStorage):
    def __init__(self, persistent_storage: IPersistentStorage, feedbot_entity, album_timeout_seconds: float):
        super(AlbumHandler, self).__init__(persistent_storage=persistent_storage)
        self.feedbot_entity = feedbot_entity
        self.album_timeout_seconds = album_timeout_seconds
        self.albums = dict()

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        ids_string = f"chat_id={event.chat_id} grouped_id={event.grouped_id} msg={event.message.id}"
        get_logger().info(msg=f"album handler called: {ids_string}")
        if get_chat_type_from_event(event=event) != ChatType.CHANNEL:
            get_logger().warning(msg=f"chat id={event.chat_id} is not a channel so do nothing")
            raise StopPropagation

        album_descriptor = (event.chat_id, event.grouped_id)

        if album_descriptor in self.albums:
            self.albums[album_descriptor].append(event.message)
            raise StopPropagation

        self.albums[album_descriptor] = [event.message]
        await sleep(self.album_timeout_seconds)
        aggregated_album_messages = self.albums.pop(album_descriptor)
        get_logger().debug(msg=f"album ({album_descriptor}) aggregated #{len(aggregated_album_messages)} messages")

        # no need for export link - just send username (because id wont be resolved) and msg_id.
        # it WORKS with not joined channels (public)
        chat = await event.get_chat()

        if chat.username is None:
            # private channels path
            # forward message
            forwarded_messages = await event.client.forward_messages(
                entity=self.feedbot_entity,
                as_album=True,
                messages=aggregated_album_messages)

            # send source channel info
            forwarded_messages_hashes_str = " ".join(str(get_forwarded_message_hash(msg)) for msg in forwarded_messages)
            await event.client.send_message(
                entity=self.feedbot_entity,
                message=f"{MessageType.FORWARD_SOURCE.name} {event.chat_id} {forwarded_messages_hashes_str}")
        else:
            # public channels path
            messages_str = " ".join(str(msg.id) for msg in aggregated_album_messages)
            await event.client.send_message(
                entity=self.feedbot_entity,
                message=f"{MessageType.MESSAGE.name} {chat.username} {messages_str}")

        raise StopPropagation
