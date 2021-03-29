from abc import ABC, abstractmethod
from telethon.events import NewMessage
from .persistent_storage.base import IPersistentStorage


def get_resolve_descriptor(resolver_id: int, message_id: int):
    return resolver_id, message_id


async def resolve_entity_try_cache(client, resolvable):
    input_entity = await client.get_input_entity(resolvable)

    return await client.get_entity(input_entity)


class CallableHandlerWithStorage(ABC):
    persistent_storage: IPersistentStorage = None

    def __init__(self, persistent_storage: IPersistentStorage):
        if persistent_storage is None:
            raise RuntimeError("Persistent storage must be passed")

        self.persistent_storage = persistent_storage

    @abstractmethod
    def __call__(self, event: NewMessage.Event):
        pass
