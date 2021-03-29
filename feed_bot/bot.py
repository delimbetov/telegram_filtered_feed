from asyncio import gather
from telethon import TelegramClient, events

from common.handler import resolve_entity_try_cache
from common.logging import get_logger
from common.persistent_storage.factory import PersistenceConfig
from common.client import CommonConfig, ClientWithPersistentStorage

from handlers.forwarders import ForwardersHandler
from handlers.help import HelpHandler
from handlers.list import ListHandler
from handlers.follow import FollowHandler
from handlers.forwarded_message import ForwardedMessageHandler
from handlers.unfollow import UnfollowHandler
from handlers.start import StartHandler
from handlers.stop import StopHandler
from handlers.all import AllHandler
from handlers.resolver_replies import ResolverRepliesHandler


class BotConfig(CommonConfig):
    def __init__(
            self,
            api_id: int,
            api_hash: str,
            token: str,
            dev_key: str,
            resolver_usernames: list,
            forwarders_user_ids: set,
            resolve_max_wait_count: int,
            resolve_timeout_seconds: float,
            resolve_warning_wait_number: int,
            forward_max_wait_count: int,
            forward_timeout_seconds: float,
            persistence_config: PersistenceConfig):
        super(BotConfig, self).__init__(
            api_id=api_id, api_hash=api_hash, persistence_config=persistence_config)

        if token is None or len(token) < 1:
            raise RuntimeError("Invalid token: " + token)

        if resolver_usernames is None or len(resolver_usernames) < 1:
            raise RuntimeError("Invalid resolver_usernames: none or empty")

        if forwarders_user_ids is None or len(forwarders_user_ids) < 1:
            raise RuntimeError("Invalid forwarders_user_ids: none or empty")

        if resolve_max_wait_count < 1:
            raise RuntimeError(f"Invalid resolve_max_wait_count={resolve_max_wait_count}")

        if resolve_timeout_seconds < 1:
            raise RuntimeError(f"Invalid resolve_timeout_seconds={resolve_timeout_seconds}")

        if resolve_warning_wait_number < 1:
            raise RuntimeError(f"Invalid resolve_warning_wait_number={resolve_warning_wait_number}")

        if forward_max_wait_count < 1:
            raise RuntimeError(f"Invalid forward_max_wait_count={forward_max_wait_count}")

        if forward_timeout_seconds < 1:
            raise RuntimeError(f"Invalid forward_timeout_seconds={forward_timeout_seconds}")

        self.token = token
        self.dev_key = dev_key
        self.resolver_usernames = resolver_usernames
        self.forwarders_user_ids = forwarders_user_ids
        self.resolve_max_wait_count = resolve_max_wait_count
        self.resolve_timeout_seconds = resolve_timeout_seconds
        self.resolve_warning_wait_number = resolve_warning_wait_number
        self.forward_max_wait_count = forward_max_wait_count
        self.forward_timeout_seconds = forward_timeout_seconds

    def __repr__(self):
        return super(BotConfig, self).__repr__() + f", token=***, dev_key=***, " \
                                                   f"resolver_usernames={self.resolver_usernames}, " \
                                                   f"forwarders_user_ids={self.forwarders_user_ids}, " \
                                                   f"resolve_max_wait_count={self.resolve_max_wait_count}, " \
                                                   f"resolve_timeout_seconds={self.resolve_timeout_seconds}, " \
                                                   f"resolve_warning_wait_number={self.resolve_warning_wait_number}, " \
                                                   f"forward_max_wait_count={self.forward_max_wait_count}, " \
                                                   f"forward_timeout_seconds={self.forward_timeout_seconds}"


class Bot(ClientWithPersistentStorage):
    def __init__(self, config: BotConfig):
        if config is None:
            raise RuntimeError("No config passed")

        self.config = config
        get_logger().info(msg="Creating Bot object with config: {}".format(self.config))

        super(Bot, self).__init__(
            client=TelegramClient(
                'feed_bot',
                api_id=config.api_id,
                api_hash=config.api_hash).start(bot_token=config.token),
            persistence_config=self.config.persistence_config)

        # prepare resolver stuff
        get_logger().info(f"Resolving resolvers usernames={self.config.resolver_usernames}")
        resolve_tasks = [
            resolve_entity_try_cache(self.client, resolver_username)
            for resolver_username in self.config.resolver_usernames]
        resolver_entities = self.client.loop.run_until_complete(gather(*resolve_tasks))
        resolver_replies = dict()

        # Add forwarders forwards handler
        self.client.add_event_handler(
            callback=ForwardersHandler(
                persistent_storage=self.persistent_storage,
                forwarders_user_ids=self.config.forwarders_user_ids,
                max_wait_count=self.config.forward_max_wait_count,
                timeout_seconds=self.config.forward_timeout_seconds),
            event=events.NewMessage(from_users=self.config.forwarders_user_ids, incoming=True, outgoing=False))

        # Add resolver replies handler
        self.client.add_event_handler(
            callback=ResolverRepliesHandler(resolver_replies=resolver_replies),
            event=events.NewMessage(from_users=resolver_entities, incoming=True, outgoing=False))

        # Add help handler
        self.client.add_event_handler(
            callback=HelpHandler(persistent_storage=self.persistent_storage),
            event=events.NewMessage(pattern=r'^/help', forwards=False, incoming=True, outgoing=False))

        # Add list handler
        self.client.add_event_handler(
            callback=ListHandler(persistent_storage=self.persistent_storage),
            event=events.NewMessage(pattern=r'^/list', forwards=False, incoming=True, outgoing=False))

        # Add start handler
        self.client.add_event_handler(
            callback=StartHandler(persistent_storage=self.persistent_storage),
            event=events.NewMessage(pattern=r'^/start', forwards=False, incoming=True, outgoing=False))
        self.client.add_event_handler(
            callback=StopHandler(persistent_storage=self.persistent_storage),
            event=events.NewMessage(pattern=r'^/stop', forwards=False, incoming=True, outgoing=False))

        # Add follow handlers
        # Multiple aliases are provided for follow command, but dont put all of these into interface to not confuse
        self.client.add_event_handler(
            callback=ForwardedMessageHandler(persistent_storage=self.persistent_storage),
            event=events.NewMessage(forwards=True, incoming=True, outgoing=False))
        self.client.add_event_handler(
            callback=FollowHandler(
                persistent_storage=self.persistent_storage,
                resolver_entities=resolver_entities,
                resolver_replies=resolver_replies,
                resolve_max_wait_count=self.config.resolve_max_wait_count,
                resolve_timeout_seconds=self.config.resolve_timeout_seconds,
                resolve_warning_wait_number=self.config.resolve_warning_wait_number),
            event=events.NewMessage(pattern=r'^/(follow|add|enroll)', forwards=False, incoming=True, outgoing=False))

        # Un follow handlers
        # NOTE: must be added before follow, or follow is
        self.client.add_event_handler(
            callback=UnfollowHandler(
                persistent_storage=self.persistent_storage,
                resolver_entities=resolver_entities,
                resolver_replies=resolver_replies,
                resolve_max_wait_count=self.config.resolve_max_wait_count,
                resolve_timeout_seconds=self.config.resolve_timeout_seconds,
                resolve_warning_wait_number=self.config.resolve_warning_wait_number),
            event=events.NewMessage(
                pattern=r'^/(unfollow|del|drop|kick|remove)', forwards=False, incoming=True, outgoing=False))

        # Admin commands
        # Add announce command
        self.client.add_event_handler(
            callback=AllHandler(persistent_storage=self.persistent_storage, key=self.config.dev_key),
            event=events.NewMessage(pattern=r'^/all', forwards=False, incoming=True, outgoing=False))

        # TODO: print hello message w request to type /start somehow
        # TODO: do something on irrelevant msgs?
        # dp.add_handler(MessageHandler(???))
