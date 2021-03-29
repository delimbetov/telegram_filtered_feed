from datetime import datetime, timedelta
from asyncio import gather, sleep
from typing import Optional

from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest

from common.handler import resolve_entity_try_cache
from common.logging import get_logger
from common.persistent_storage.factory import PersistenceConfig
from common.client import CommonConfig, ClientWithPersistentStorage
from common.telegram import contains_joinchat_link, join_link

from handlers.message import MessageHandler
from handlers.album import AlbumHandler

from common.interval import MultiInterval


class ForwarderConfig(CommonConfig):
    def __init__(
            self,
            api_id: int,
            api_hash: str,
            monitored_chats_id_interval: MultiInterval,
            persistence_config: PersistenceConfig,
            feedbot_username: str,
            modification_time_handicap_seconds: int,
            validation_hour: int,
            album_timeout_seconds: float):
        super(ForwarderConfig, self).__init__(
            api_id=api_id, api_hash=api_hash, persistence_config=persistence_config)
        self.monitored_chats_id_interval = monitored_chats_id_interval
        self.feedbot_username = feedbot_username
        self.modification_time_handicap_seconds = modification_time_handicap_seconds
        self.validation_hour = validation_hour
        self.album_timeout_seconds = album_timeout_seconds

    def __repr__(self):
        return super(ForwarderConfig, self).__repr__()\
               + f", feedbot_username={self.feedbot_username}" \
                 f", monitored_chats_id_interval={self.monitored_chats_id_interval}" \
                 f", modification_time_handicap_seconds={self.modification_time_handicap_seconds}" \
                 f", validation_hour={self.validation_hour}" \
                 f", album_timeout_seconds={self.album_timeout_seconds}"


class Forwarder(ClientWithPersistentStorage):
    # ClientWithPersistentStorage overrides
    async def prepare(self):
        # Sub to list of notifies
        get_logger().info("Subbing to notifies ...")
        await self.persistent_storage.subscribe(notifies_to_handlers=self.notifies_to_handlers)
        get_logger().info("Ensure joined and db channels are in sync")
        await self.compare_telegram_subs_with_db()

    def get_continuous_async_tasks(self):
        return super(Forwarder, self).get_continuous_async_tasks() + [
            self.persistent_storage.listen(
                notifies_to_handlers=self.notifies_to_handlers,
                should_run_func=self.client.is_connected),
            self.validation_task()]

    # Forwarder
    async def get_monitored_chats_delta(self, prev_max_time: Optional[str]):
        chat_to_enabled_joiner_dict, new_max_time = await self.persistent_storage.get_monitored_channels_delta(
            handicap_seconds=self.config.modification_time_handicap_seconds,
            prev_max_time=prev_max_time,
            monitored_chats_id_interval=self.config.monitored_chats_id_interval)
        get_logger().info(f"Max monitored channels mod time {self.monitored_channels_max_mod_time} -> {new_max_time}")
        self.monitored_channels_max_mod_time = new_max_time

        return chat_to_enabled_joiner_dict

    async def validation_task(self):
        get_logger().info("Starting validation task")

        while True:
            now = datetime.today()
            future = datetime(now.year, now.month, now.day, self.config.validation_hour, 0)
            if now.hour >= self.config.validation_hour:
                future += timedelta(days=1)
            sleep_seconds = (future - now).seconds
            get_logger().info(f"Validation task: sleep for {sleep_seconds} seconds")
            await sleep(sleep_seconds)
            await self.compare_telegram_subs_with_db()

    async def on_subscriptions_update(self):
        get_logger().info("Handler for subscriptions update notify called")

        chat_to_enabled_joiner_dict = await self.get_monitored_chats_delta(
            prev_max_time=self.monitored_channels_max_mod_time)
        enabled_joiners = [joiner for chat_id, (enabled, joiner) in chat_to_enabled_joiner_dict.items() if enabled]
        get_logger().info(f"Delta monitored_channels enabled count={len(enabled_joiners)}: {enabled_joiners}")

        # join missing
        await self.join_chats(joiners=enabled_joiners)

    async def join_username(self, username: str):
        # sometimes channels might get deleted so they wont resolve
        input_entity = await self.client.get_input_entity(username)

        return await self.client(JoinChannelRequest(input_entity))

    async def join_chat(self, joiner: str):
        get_logger().info(f"Joining channel using={joiner}")
        join_task = join_link(client=self.client, link=joiner)\
            if contains_joinchat_link(arg=joiner)\
            else self.join_username(username=joiner)
        result = await join_task
        get_logger().debug(f"Joined channel using={joiner} result={result}")

        return True

    async def join_chats(self, joiners: list):
        results = await gather(*[self.join_chat(joiner=joiner) for joiner in joiners], return_exceptions=True)

        # report errors
        for res, joiner in zip(results, joiners):
            if not isinstance(res, bool) or not res:
                get_logger().error(f"Failed to join channel={joiner}: {str(res)}")

    async def compare_telegram_subs_with_db(self):
        get_logger().info("Running subs validation")
        # Get chats that are actualy joined in telegram
        get_logger().debug("Getting telegram dialogs")
        # dialog.id from iter_dialogs is confirmed to be without alterations
        joined_chat_ids = [dialog.id async for dialog in self.client.iter_dialogs()]
        get_logger().debug(f"Got {len(joined_chat_ids)} dialogs")

        # Get chats to monitor from db
        chat_to_enabled_joiner_dict = await self.get_monitored_chats_delta(prev_max_time=None)

        # Now compare
        joined_not_in_db = [chat_id for chat_id in joined_chat_ids if chat_id not in chat_to_enabled_joiner_dict]
        in_db_not_joined = [joiner for chat_id, (enabled, joiner) in chat_to_enabled_joiner_dict.items()
                            if enabled and chat_id not in joined_chat_ids]
        get_logger().info(f"Joined chats that are missing in db count={len(joined_not_in_db)}: {joined_not_in_db}")
        get_logger().info(f"Enabled in db chats that are not joined count={len(in_db_not_joined)}: {in_db_not_joined}")

        # join missing
        await self.join_chats(joiners=in_db_not_joined)

    def __init__(self, config: ForwarderConfig):
        if config is None:
            raise RuntimeError("No config passed")

        self.config = config
        get_logger().info(msg="Creating Forwarder object with config: {}".format(self.config))
        self.monitored_channels_max_mod_time = None
        self.notifies_to_handlers = {"notify_subscriptions_updated": self.on_subscriptions_update}

        super(Forwarder, self).__init__(
            client=TelegramClient(
                'forwarder',
                api_id=config.api_id,
                api_hash=config.api_hash).start(),
            persistence_config=self.config.persistence_config)

        get_logger().info(f"Resolving feedbot_username={self.config.feedbot_username}")
        self.feedbot_entity = self.client.loop.run_until_complete(
            resolve_entity_try_cache(self.client, self.config.feedbot_username))

        # Add album handler. The order matters! Must be added before message handler
        self.client.add_event_handler(
            callback=AlbumHandler(
                persistent_storage=self.persistent_storage,
                feedbot_entity=self.feedbot_entity,
                album_timeout_seconds=self.config.album_timeout_seconds),
            event=events.NewMessage(func=lambda e: e.grouped_id, incoming=True, outgoing=False))

        # Add message handler
        self.client.add_event_handler(
            callback=MessageHandler(persistent_storage=self.persistent_storage, feedbot_entity=self.feedbot_entity),
            event=events.NewMessage(func=lambda e: not e.grouped_id, incoming=True, outgoing=False))
