from enum import Enum
from telethon.events import NewMessage
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.custom import Message


g_joinchat_prefix = "t.me/joinchat/"


class ChatType(Enum):
    PRIVATE = 0  # user x bot
    GROUP = 1  # normal private group chat
    SUPER_GROUP = 2  # public group chat/large private group?
    CHANNEL = 3  # channel


def get_chat_type_from_string(telegram_chat_type: str):
    if telegram_chat_type.lower() == "private":
        return ChatType.PRIVATE
    elif telegram_chat_type.lower() == "group":
        return ChatType.GROUP
    elif telegram_chat_type.lower() == "supergroup":
        return ChatType.SUPER_GROUP
    elif telegram_chat_type.lower() == "channel":
        return ChatType.CHANNEL

    raise RuntimeError("Unknown chat type: " + telegram_chat_type)


def get_chat_type_from_event(event: NewMessage.Event):
    if event.is_private:
        return ChatType.PRIVATE
    elif event.is_group and not event.is_channel:
        return ChatType.GROUP
    elif event.is_group and event.is_channel:
        return ChatType.SUPER_GROUP
    elif not event.is_group and event.is_channel:
        return ChatType.CHANNEL

    raise RuntimeError(f"Unknown chat type: chat_id={event.chat_id}")


def contains_joinchat_link(arg: str):
    return g_joinchat_prefix in arg


def get_hash_from_link(link: str):
    if not contains_joinchat_link(arg=link):
        raise RuntimeError("Can't get hash, its not joinchat link: " + str(link))

    return link[link.find(g_joinchat_prefix) + len(g_joinchat_prefix):]


async def join_link(client, link: str):
    link_hash = get_hash_from_link(link=link)

    return await client(ImportChatInviteRequest(hash=link_hash))


def get_monitored_chat_name(title: str, chat_id: int):
    return f"'{title}': {chat_id}"


def get_forwarded_message_hash(msg: Message):
    if msg.forward is None:
        raise RuntimeError("Message is not forward")

    # TODO: use media/text as part of the hash too?
    tpl = msg.date, msg.fwd_from.date, msg.fwd_from.channel_id, msg.fwd_from.channel_post
    return hash(tpl)
