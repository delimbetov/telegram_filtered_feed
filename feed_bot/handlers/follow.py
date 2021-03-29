from telethon.events import NewMessage, StopPropagation
from .base import BaseFeedBotHandlerWithResolve
from common.persistent_storage.base import IPersistentStorage
from common.logging import get_logger
from common.resources.localization import get_localized, g_key_handlers_follow_already_enabled
from common.resources.localization import Language, g_key_handlers_follow_did_enable


async def follow(
        persistent_storage,
        event: NewMessage.Event,
        target_chat_id: int,
        target_title: str,
        target_joiner: str,
        language: Language):
    user_chat_id = event.chat_id

    # check if subscription is enabled already, if not add or enable it
    existed_before, enabled_before = await persistent_storage.add_or_enable_subscription(
        user_chat_id=user_chat_id,
        target_chat_id=target_chat_id,
        target_title=target_title,
        target_joiner=target_joiner)
    get_logger().debug(f"subscription for user_chat_id={user_chat_id} to target_chat_id={target_chat_id} "
                       f"({target_title}, {target_joiner}) existed_before={existed_before}, enabled_before={enabled_before}")

    if enabled_before:
        # send message to user that nothing is to be done
        await event.message.respond(
            get_localized(g_key_handlers_follow_already_enabled, language, [target_joiner]))
    else:
        # no need to handle separately existed before and not existed before
        await event.message.respond(get_localized(g_key_handlers_follow_did_enable, language, [target_joiner]))


class FollowHandler(BaseFeedBotHandlerWithResolve):
    def __init__(
            self,
            persistent_storage: IPersistentStorage,
            resolver_entities: list,
            resolver_replies: dict,
            resolve_max_wait_count: int,
            resolve_timeout_seconds: float,
            resolve_warning_wait_number: int):
        super(FollowHandler, self).__init__(
            persistent_storage=persistent_storage,
            resolver_entities=resolver_entities,
            resolver_replies=resolver_replies,
            resolve_max_wait_count=resolve_max_wait_count,
            resolve_timeout_seconds=resolve_timeout_seconds,
            resolve_warning_wait_number=resolve_warning_wait_number)

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        resolved_dict, _, locale = await self.get_resolved_chat_ids_title_joiner_from_event(
            resolver_entity_generator=self.circular_resolver_generator,
            resolver_replies=self.resolver_replies,
            max_wait_count=self.resolve_max_wait_count,
            timeout_seconds=self.resolve_timeout_seconds,
            warning_wait_number=self.resolve_warning_wait_number,
            event=event,
            is_follow=True)

        for resolved_chat_id, (title, joiner) in resolved_dict.items():
            await follow(
                persistent_storage=self.persistent_storage,
                event=event,
                target_chat_id=resolved_chat_id,
                target_title=title,
                target_joiner=joiner,
                language=locale)

        raise StopPropagation
