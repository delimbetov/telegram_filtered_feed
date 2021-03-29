from asyncio import gather, sleep
from telethon.events import NewMessage, StopPropagation
from telethon.tl.types import Channel
from common.persistent_storage.base import IPersistentStorage

from common.utils import circular_generator
from common.handler import CallableHandlerWithStorage, get_resolve_descriptor, resolve_entity_try_cache
from common.logging import get_logger
from common.telegram import contains_joinchat_link
from common.protocol import g_resolver_request_command, g_resolver_separator
from common.resources.localization import get_localized, Language, get_language_from_ietf_code
from common.resources.localization import g_key_handlers_follow_unfollow_no_args, g_key_handlers_failed_to_resolve
from common.resources.localization import g_key_handlers_not_enrolled, g_key_handlers_no_username
from common.resources.localization import g_key_handlers_resolve_might_take_time


async def get_sender_and_language_from_event(event: NewMessage.Event) -> tuple:
    sender = await event.message.get_sender()
    # language code might be none but its accounted for in function
    language = get_language_from_ietf_code(sender.lang_code)

    return sender, language


async def query_resolver(
        resolver_entity,
        resolver_replies: dict,
        max_wait_count: int,
        timeout_seconds: float,
        warning_wait_number: int,
        event: NewMessage.Event,
        arg: str,
        locale) -> tuple:
    get_logger().info(msg=f"{arg} is joinchat link, assuming it's to private channel; query resolver")

    # send resolve request to resolver
    sent_message = await event.client.send_message(resolver_entity, f"{g_resolver_request_command} {arg}")
    resolver_id = await event.client.get_peer_id(resolver_entity)
    resolve_descriptor = get_resolve_descriptor(resolver_id=resolver_id, message_id=sent_message.id)

    # await reply to that request; but don't wait forever: raise on timeout
    waits = 1
    while resolve_descriptor not in resolver_replies:
        if max_wait_count < waits:
            err_msg = f"Failed to wait for resolver' reply to {resolve_descriptor}: it was not received"
            get_logger().warning(msg=err_msg)
            await event.message.respond(get_localized(g_key_handlers_failed_to_resolve, locale, [arg]))
            raise RuntimeError(f"Failed to resolve {arg}: {err_msg}")

        if waits == warning_wait_number:
            await event.message.respond(get_localized(g_key_handlers_resolve_might_take_time, locale, [arg]))

        get_logger().debug(f"waiting for resolver' reply to {resolve_descriptor}, wait#{waits} for {timeout_seconds}s")
        await sleep(timeout_seconds)
        waits += 1

    reply_text = resolver_replies.pop(resolve_descriptor)
    get_logger().debug(f"reply to={resolve_descriptor} was received={reply_text}")

    # parse reply
    return tuple(reply_text.split(g_resolver_separator))


async def get_resolved_arg(
        resolver_entity,
        resolver_replies: dict,
        max_wait_count: int,
        timeout_seconds: float,
        warning_wait_number: int,
        event: NewMessage.Event,
        arg: str,
        locale) -> tuple:
    if contains_joinchat_link(arg=arg):
        return await query_resolver(
            resolver_entity=resolver_entity,
            resolver_replies=resolver_replies,
            max_wait_count=max_wait_count,
            timeout_seconds=timeout_seconds,
            warning_wait_number=warning_wait_number,
            event=event,
            arg=arg,
            locale=locale)
    else:
        entity = None

        # get channel from arg; getting full entities for username
        # query input entities first to maximize use of cache
        try:
            entity = await resolve_entity_try_cache(event.client, arg)
        except Exception as e:
            get_logger().warning(msg=f"Failed to resolve arg={arg}: {str(e)}")
            await event.message.respond(get_localized(g_key_handlers_failed_to_resolve, locale, [arg]))
            raise RuntimeError(f"Failed to resolve {arg}: {str(e)}")

        if not isinstance(entity, Channel):
            get_logger().warning(msg=f"Failed to resolve arg={arg}")
            await event.message.respond(get_localized(g_key_handlers_failed_to_resolve, locale, [arg]))
            raise RuntimeError(f"Failed to resolve {arg}: not a channel")

        if entity.username is None:
            get_logger().warning(f"Can't follow arg={arg}: it has no username: {str(entity)}")
            await event.message.respond(get_localized(g_key_handlers_no_username, locale, [arg]))
            raise RuntimeError(f"Failed to resolve {arg}: no username")

        chat_id = await event.client.get_peer_id(entity)

        return chat_id, entity.title, entity.username


class BaseFeedBotHandler(CallableHandlerWithStorage):
    def __init__(self, persistent_storage: IPersistentStorage):
        super(BaseFeedBotHandler, self).__init__(persistent_storage=persistent_storage)

    async def assert_enrolled(self, event: NewMessage.Event) -> Language:
        user_chat_id = event.chat_id
        is_enrolled, locale = await self.persistent_storage.get_user_enrolled_and_locale(user_chat_id=user_chat_id)

        if not is_enrolled:
            _, locale = await get_sender_and_language_from_event(event=event)
            get_logger().debug(msg=f"Chat id={user_chat_id} is not enrolled so ignore command")
            await event.message.respond(get_localized(g_key_handlers_not_enrolled, locale))
            raise StopPropagation

        return locale

    async def get_resolved_chat_ids_title_joiner_from_event(
            self,
            resolver_entity_generator,
            resolver_replies: dict,
            max_wait_count: int,
            timeout_seconds: float,
            warning_wait_number: int,
            event: NewMessage.Event,
            is_follow: bool):
        chat_id = event.chat_id
        try_digit_args = not is_follow
        handler_name = "follow" if is_follow else "unfollow"

        # first argument is command
        split_args = event.message.message.split(' ')[1:]
        resolvable_args = []
        digit_args = []

        for arg in split_args:
            if len(arg) > 0:
                if try_digit_args:
                    try:
                        # it works because username can't be a number
                        chat_id_arg = int(arg)
                        digit_args.append(chat_id_arg)
                    except ValueError:
                        resolvable_args.append(arg)
                else:
                    resolvable_args.append(arg)

        get_logger().info(msg=f"{handler_name} handler called: chat_id={chat_id} "
                              f"resolvable_args={resolvable_args} digit_args={digit_args}")

        # assert user is enrolled
        locale = await self.assert_enrolled(event=event)

        if len(resolvable_args) < 1 and len(digit_args) < 1:
            get_logger().debug(msg=f"No args for {handler_name} command")
            await event.message.respond(get_localized(g_key_handlers_follow_unfollow_no_args, locale, [handler_name]))
            raise StopPropagation

        # return exceptions so on failure to resolve other resolves don't fail
        resolve_tasks = [
            get_resolved_arg(
                resolver_entity=next(resolver_entity_generator),
                resolver_replies=resolver_replies,
                max_wait_count=max_wait_count,
                timeout_seconds=timeout_seconds,
                warning_wait_number=warning_wait_number,
                event=event,
                arg=arg,
                locale=locale) for arg in resolvable_args]
        chat_id_title_joiner_tuples = await gather(*resolve_tasks, return_exceptions=True)

        # filter exceptions
        chat_id_title_joiner_tuples = [tpl for tpl in chat_id_title_joiner_tuples if isinstance(tpl, tuple)]

        # use dict to filter duplicate ids
        resolved_dict = {
            resolved_chat_id: (title, joiner)
            for resolved_chat_id, title, joiner in chat_id_title_joiner_tuples}
        get_logger().debug(
            f"args={resolvable_args} resolved into="
            f"{[tpl for tpl in resolved_dict.items()]}")

        return resolved_dict, digit_args, locale


class BaseFeedBotHandlerWithResolve(BaseFeedBotHandler):
    def __init__(
            self,
            persistent_storage: IPersistentStorage,
            resolver_entities: list,
            resolver_replies: dict,
            resolve_max_wait_count: int,
            resolve_timeout_seconds: float,
            resolve_warning_wait_number: int):
        super(BaseFeedBotHandlerWithResolve, self).__init__(persistent_storage=persistent_storage)
        self.circular_resolver_generator = circular_generator(resolver_entities)
        self.resolver_replies = resolver_replies
        self.resolve_max_wait_count = resolve_max_wait_count
        self.resolve_timeout_seconds = resolve_timeout_seconds
        self.resolve_warning_wait_number = resolve_warning_wait_number
