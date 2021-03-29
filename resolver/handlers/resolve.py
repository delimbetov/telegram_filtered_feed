from asyncio import sleep

from telethon.events import NewMessage, StopPropagation
from telethon.tl.functions.channels import LeaveChannelRequest
from telethon.tl.functions.messages import DeleteChatUserRequest
from telethon.tl.types import Channel
from telethon.errors.rpcerrorlist import UserAlreadyParticipantError

from common.logging import get_logger
from common.telegram import contains_joinchat_link, join_link, get_monitored_chat_name
from common.protocol import g_resolver_response_error_prefix, g_resolver_separator


class ResolveHandler:
    def __init__(self, join_tries: int):
        self.join_tries = join_tries

    async def __call__(self, event: NewMessage.Event):
        get_logger().info(msg=f"resolve handler called: chat_id={event.chat_id} msg={event.message.message}")
        split_args = event.message.message.split(' ')[1:]

        if len(split_args) != 1:
            get_logger().warning(msg=f"chat id={event.chat_id} sent message with invalid args={split_args}")
            await event.message.reply(f"{g_resolver_response_error_prefix}: message with invalid args={split_args}")
            raise StopPropagation

        joinchat_arg = split_args[0]
        if not contains_joinchat_link(arg=joinchat_arg):
            get_logger().warning(msg=f"chat id={event.chat_id} sent message without joinchat link")
            await event.message.reply(f"{g_resolver_response_error_prefix}: message without joinchat link")
            raise StopPropagation

        # join that chat
        joined_chats = []
        did_join = True
        tries = 1

        while self.join_tries >= tries:
            try:
                join_updates = await join_link(client=event.client, link=joinchat_arg)
                joined_chats = join_updates.chats
                break
            except UserAlreadyParticipantError as user_participant_exc:
                # eg if we didn't leave it for some reason OR concurrent task joined it
                get_logger().debug(f"Already participant: {str(user_participant_exc)}")

                try:
                    entity = await event.client.get_entity(joinchat_arg)
                    joined_chats = [entity]
                    did_join = False
                    break
                except Exception as e:
                    get_logger().warning(f"Failed to join link & resolve entity: {str(e)}")
                    await sleep(1)
                    tries += 1
            except Exception as exc:
                get_logger().error(f"Unexpected join error: {str(exc)}")
                await event.message.reply(f"{g_resolver_response_error_prefix}: {str(exc)}")
                raise StopPropagation

        if len(joined_chats) != 1:
            err_msg = f"invalid amount of chats joined/updated: #={len(joined_chats)}"
            get_logger().warning(msg=err_msg)
            await event.message.reply(f"{g_resolver_response_error_prefix}: {err_msg}")
            raise StopPropagation

        resolved_chat = joined_chats[0]
        resolved_chat_id = await event.client.get_peer_id(resolved_chat)
        resolved_title = resolved_chat.title
        resolved_joiner = joinchat_arg

        # respond with resolved stuff
        get_logger().debug(f"joinchat={joinchat_arg} resolved into "
                           f"{get_monitored_chat_name(title=resolved_title, chat_id=resolved_chat_id)}")
        await event.message.reply(
            g_resolver_separator.join([str(resolved_chat_id), str(resolved_title), str(resolved_joiner)]))

        # leave that chat
        if did_join:
            if isinstance(resolved_chat, Channel):
                leave_updates = await event.client(LeaveChannelRequest(resolved_chat))
                if len(leave_updates.chats) != 1:
                    # do not reply with error to sender, because it already received resolved results
                    get_logger().warning(msg=f"invalid amount of channels leaved/updated: "
                                             f"#={len(leave_updates.chats)}, {str(leave_updates)}")
                    raise StopPropagation
            else:
                leave_updates = await event.client(DeleteChatUserRequest(chat_id=resolved_chat_id, user_id='me'))
                if len(leave_updates.chats) != 1:
                    # do not reply with error to sender, because it already received resolved results
                    get_logger().warning(msg=f"invalid amount of chats leaved/updated: "
                                             f"#={len(leave_updates.chats)}, {str(leave_updates)}")
                    raise StopPropagation

        raise StopPropagation
