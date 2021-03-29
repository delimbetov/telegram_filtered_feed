from telethon.events import NewMessage, StopPropagation

from common.handler import get_resolve_descriptor
from common.logging import get_logger


class ResolverRepliesHandler:
    def __init__(self, resolver_replies: dict):
        self.resolver_replies = resolver_replies

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        sender_id = event.message.from_id
        reply_to_msg_id = event.message.reply_to_msg_id
        resolve_descriptor = get_resolve_descriptor(resolver_id=sender_id, message_id=reply_to_msg_id)
        resolve_text = event.message.message
        get_logger().info(msg=f"resolved replies handler called: resolve_descriptor={resolve_descriptor} "
                              f"resolve text={resolve_text}")

        # it should never happen, but lets just overwrite old text while logging error
        if resolve_descriptor in self.resolver_replies:
            get_logger().error(msg=f"for some reason resolve_descriptor={resolve_descriptor} is already present: "
                                   f"old text={self.resolver_replies[resolve_descriptor]} "
                                   f"new text={resolve_text}")

        self.resolver_replies[resolve_descriptor] = resolve_text

        raise StopPropagation
