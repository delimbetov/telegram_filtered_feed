from asyncio import gather

from telethon import TelegramClient, events

from common.logging import get_logger
from common.client import BaseClientConfig, Client
from common.protocol import g_resolver_request_command
from common.handler import resolve_entity_try_cache

from handlers.resolve import ResolveHandler


class ResolverConfig(BaseClientConfig):
    def __init__(
            self,
            api_id: int,
            api_hash: str,
            join_tries: int,
            from_usernames: list):
        super(ResolverConfig, self).__init__(api_id=api_id, api_hash=api_hash)
        self.join_tries = join_tries
        self.from_usernames = from_usernames

    def __repr__(self):
        return super(ResolverConfig, self).__repr__() + \
               f", join_tries={self.join_tries}, from_usernames={self.from_usernames}"


# TODO: at some point add validation task that will leave all joined chats
class Resolver(Client):
    def __init__(self, config: ResolverConfig):
        if config is None:
            raise RuntimeError("No config passed")

        super(Resolver, self).__init__(
            client=TelegramClient(
                'resolver',
                api_id=config.api_id,
                api_hash=config.api_hash).start())

        self.config = config
        get_logger().info(msg="Creating Resolver object with config: {}".format(self.config))

        # resolve from usernames
        get_logger().info(f"Resolving from_usernames={self.config.from_usernames}")
        resolve_tasks = [
            resolve_entity_try_cache(self.client, username)
            for username in self.config.from_usernames]
        self.from_entities = self.client.loop.run_until_complete(gather(*resolve_tasks))

        # Add resolve handler
        self.client.add_event_handler(
            callback=ResolveHandler(join_tries=self.config.join_tries),
            event=events.NewMessage(
                pattern=f'^{g_resolver_request_command}', forwards=False, incoming=True, outgoing=False,
                from_users=self.from_entities))
