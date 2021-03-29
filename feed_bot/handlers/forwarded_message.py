from asyncio import gather
from telethon.events import NewMessage, StopPropagation
from telethon.tl.types import Channel
from common.persistent_storage.base import IPersistentStorage
from .base import BaseFeedBotHandler
from .follow import follow
from common.logging import get_logger
from common.resources.localization import get_localized, g_key_handlers_forwarded_message_not_channel
from common.resources.localization import g_key_handlers_forwarded_message_not_public


class ForwardedMessageHandler(BaseFeedBotHandler):
    def __init__(self, persistent_storage: IPersistentStorage):
        super(ForwardedMessageHandler, self).__init__(persistent_storage=persistent_storage)

    # FollowHandler
    async def __call__(self, event: NewMessage.Event):
        chat_id = event.chat_id

        if not event.is_private:
            get_logger().debug(msg=f"forwarded message ignored since chat is not private: chat_id={chat_id}")
            raise StopPropagation

        # assert user is enrolled
        locale, forwarded_from_chat = await gather(self.assert_enrolled(event=event), event.message.forward.get_chat())
        forwarded_chat_entity = await event.client.get_input_entity(forwarded_from_chat)
        forwarded_chat_resolved_id = await event.client.get_peer_id(forwarded_chat_entity)

        get_logger().info(msg=f"forwarded message handler called: chat_id={chat_id} "
                              f"source_chat_id={forwarded_chat_resolved_id}")

        if not isinstance(forwarded_from_chat, Channel):
            get_logger().info(msg=f"source chat id={forwarded_chat_resolved_id} is not channel so ignore forwarding")
            await event.message.respond(get_localized(g_key_handlers_forwarded_message_not_channel, locale))
            raise StopPropagation

        if forwarded_from_chat.username is None:
            get_logger().info(msg=f"source chat id={forwarded_chat_resolved_id} "
                                  f"doesn't have username so its prolly private channel")
            await event.message.respond(get_localized(g_key_handlers_forwarded_message_not_public, locale))
            raise StopPropagation

        await follow(
            self.persistent_storage,
            event=event,
            target_chat_id=forwarded_chat_resolved_id,
            target_title=forwarded_from_chat.title,
            target_joiner=forwarded_from_chat.username,
            language=locale)

        raise StopPropagation
