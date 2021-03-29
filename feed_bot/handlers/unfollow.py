from asyncio import gather

from telethon.events import NewMessage, StopPropagation
from .base import BaseFeedBotHandlerWithResolve
from common.telegram import get_monitored_chat_name
from common.persistent_storage.base import IPersistentStorage
from common.logging import get_logger
from common.resources.localization import Language, get_localized
from common.resources.localization import g_key_handlers_unfollow_not_followed, g_key_handlers_unfollow_did_disable


class UnfollowHandler(BaseFeedBotHandlerWithResolve):
    def __init__(
            self,
            persistent_storage: IPersistentStorage,
            resolver_entities: list,
            resolver_replies: dict,
            resolve_max_wait_count: int,
            resolve_timeout_seconds: float,
            resolve_warning_wait_number: int):
        super(UnfollowHandler, self).__init__(
            persistent_storage=persistent_storage,
            resolver_entities=resolver_entities,
            resolver_replies=resolver_replies,
            resolve_max_wait_count=resolve_max_wait_count,
            resolve_timeout_seconds=resolve_timeout_seconds,
            resolve_warning_wait_number=resolve_warning_wait_number)

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        # usernames are resolved and numeric arguments are given back as chat_id_args
        resolved_dict, chat_id_args, locale = await self.get_resolved_chat_ids_title_joiner_from_event(
            resolver_entity_generator=self.circular_resolver_generator,
            resolver_replies=self.resolver_replies,
            max_wait_count=self.resolve_max_wait_count,
            timeout_seconds=self.resolve_timeout_seconds,
            warning_wait_number=self.resolve_warning_wait_number,
            event=event,
            is_follow=False)

        unfollow_tasks = [
            self.unfollow(
                event=event,
                target_chat_id=chat_id,
                arg=get_monitored_chat_name(title=title, chat_id=chat_id),
                language=locale) for chat_id, (title, joiner) in resolved_dict.items()]
        unfollow_tasks += [
            self.unfollow(
                event=event, target_chat_id=chat_id, arg=chat_id, language=locale) for chat_id in chat_id_args]
        await gather(*unfollow_tasks)

        raise StopPropagation

    # Internal
    async def unfollow(
            self,
            event: NewMessage.Event,
            target_chat_id: int,
            arg: str,
            language: Language):
        # title/joiner might be null here if there's no db record w that target_chat_id
        enabled_before, disabled_now, title, joiner = await self.persistent_storage.disable_subscription(
            user_chat_id=event.chat_id, target_chat_id=target_chat_id)
        get_logger().debug(f"user chat id={event.chat_id} disabling subscription to (title, joiner)=({title}"
                           f", {joiner}), enabled_before={enabled_before}, disabled_now={disabled_now}")

        if not enabled_before and not disabled_now:
            # if there was no subscription
            await event.message.respond(get_localized(g_key_handlers_unfollow_not_followed, language, [arg]))
        elif disabled_now != enabled_before:
            # if there was subscription but it was disabled already
            await event.message.respond(
                get_localized(
                    g_key_handlers_unfollow_not_followed,
                    language,
                    [get_monitored_chat_name(title=title, chat_id=target_chat_id)]))
        else:
            # if there was subscription so unfollow actually happened
            await event.message.respond(
                get_localized(
                    g_key_handlers_unfollow_did_disable,
                    language,
                    [get_monitored_chat_name(title=title, chat_id=target_chat_id)]))
