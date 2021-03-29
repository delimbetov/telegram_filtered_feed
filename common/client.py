from asyncio import gather
from telethon import TelegramClient
from .logging import get_logger
from .persistent_storage.factory import PersistenceConfig, create_persistent_storage


class BaseClientConfig:
    def __init__(self, api_id: int, api_hash: str):
        if api_id is None:
            raise RuntimeError("Api id must be set")

        if api_hash is None or len(api_hash) < 1:
            raise RuntimeError("Invalid api_hash: " + api_hash)

        self.api_id = api_id
        self.api_hash = api_hash

    def __repr__(self):
        return "App id=***, app hash=***"


class CommonConfig(BaseClientConfig):
    def __init__(
            self,
            api_id: int,
            api_hash: str,
            persistence_config: PersistenceConfig):
        super(CommonConfig, self).__init__(api_id=api_id, api_hash=api_hash)

        if persistence_config is None:
            raise RuntimeError("No persistence config")

        self.persistence_config = persistence_config

    def __repr__(self):
        return super(CommonConfig, self).__repr__() + ", persistence config=({})".format(self.persistence_config)


class Client:
    def __init__(self, client: TelegramClient):
        self.client = client

    # these are for overriding
    async def prepare(self):
        pass

    def get_continuous_async_tasks(self):
        return [self.client.run_until_disconnected()]

    # TODO: fix errors on termination
    async def arun(self):
        get_logger().info("Preparing ... ")
        await self.prepare()

        # get_logger().info("Catching up ... ")
        # DO NOT CATCHUP UNTIL ITS FIXED
        # await self.client.catch_up()
        # get_logger().info("Catching up complete")
        # TODO: somehow process errors in async tasks  (except main client loop - its working already)
        await gather(*self.get_continuous_async_tasks())

    def run(self):
        get_logger().info("Starting run loop ...")

        with self.client:
            get_logger().info("Starting async run loop ... ")
            self.client.loop.run_until_complete(self.arun())
            get_logger().info("... async run loop is stopped")

        get_logger().info("... run loop is stopped")


class ClientWithPersistentStorage(Client):
    def __init__(self, client: TelegramClient, persistence_config: PersistenceConfig):
        super(ClientWithPersistentStorage, self).__init__(client=client)

        # Prepare bot for running
        # Load/create persistent storage
        self.persistent_storage = create_persistent_storage(persistence_config=persistence_config)

    async def arun(self):
        async with self.persistent_storage:
            await super(ClientWithPersistentStorage, self).arun()
