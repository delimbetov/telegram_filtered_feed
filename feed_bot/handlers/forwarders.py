from asyncio import gather, sleep

from telethon.events import NewMessage, StopPropagation

from .base import BaseFeedBotHandler
from common.persistent_storage.base import IPersistentStorage
from common.logging import get_logger
from common.protocol import MessageType
from common.telegram import get_forwarded_message_hash


class ForwardersHandler(BaseFeedBotHandler):
    def __init__(
            self,
            persistent_storage: IPersistentStorage,
            forwarders_user_ids: set,
            max_wait_count: int,
            timeout_seconds: float):
        super(ForwardersHandler, self).__init__(persistent_storage=persistent_storage)
        self.forwarders_user_ids = forwarders_user_ids
        self.forwards = dict()
        self.max_wait_count = max_wait_count
        self.timeout_seconds = timeout_seconds

    # helpers
    def accumulate_forward(self, event: NewMessage.Event):
        msg_hash = get_forwarded_message_hash(event.message)
        get_logger().debug(msg=f"accumulate_forward called, msg id={event.message.id} hash={msg_hash}")

        if msg_hash not in self.forwards:
            self.forwards[msg_hash] = list()

        self.forwards[msg_hash].append(event.message)

    def pop_list_if_empty(self, msg_hash: int):
        # erase whole list if list is now empty
        if len(self.forwards[msg_hash]) == 0:
            self.forwards.pop(msg_hash)

    def take_first_forward(self, msg_hash: int):
        msg = self.forwards[msg_hash].pop(0)
        self.pop_list_if_empty(msg_hash=msg_hash)

        return msg

    def erase_forwards(self, hashes: list):
        for msg_hash in hashes:
            if msg_hash in self.forwards:
                # erase first element for that hash
                if len(self.forwards[msg_hash]) > 0:
                    self.take_first_forward(msg_hash=msg_hash)
                else:
                    # if take_first_forward was called its already popped
                    self.pop_list_if_empty(msg_hash=msg_hash)

    async def forward_messages(
            self,
            event: NewMessage.Event,
            forwarded_message_type: MessageType,
            forwarded_from_chat_id: int,
            forwards_count: int,
            **kwargs_forward):
        # query subs for forwarded chat id
        subbed_user_chat_ids = await self.persistent_storage.get_channel_subscribers(chat_id=forwarded_from_chat_id)
        get_logger().debug(msg=f"Forward {forwarded_message_type.name} #{forwards_count} "
                               f"from={forwarded_from_chat_id} to {len(subbed_user_chat_ids)} "
                               f"subs: {subbed_user_chat_ids}")

        # forward message to each sub
        forwarded_messages = await gather(
            *[event.client.forward_messages(
                entity=user_chat_id,
                as_album=forwards_count > 1,
                **kwargs_forward) for user_chat_id in subbed_user_chat_ids],
            return_exceptions=True)
        successes = [messages for messages in forwarded_messages if isinstance(messages, list) and len(messages) > 0]
        failures = [
            messages for messages in forwarded_messages if not (isinstance(messages, list) and len(messages) > 0)]
        get_logger().info(msg=f"{forwarded_message_type.name} #{forwards_count} from={forwarded_from_chat_id} "
                              f"was forwarded to {len(successes)} chats; failures #{len(failures)}={failures}")

    # CallableHandlerWithStorage
    async def __call__(self, event: NewMessage.Event):
        get_logger().info(msg=f"forwarders handler called, chat_id={event.chat_id}")

        # assert its forwarder
        if event.message.from_id not in self.forwarders_user_ids:
            get_logger().error(
                msg=f"user id={event.message.from_id} is not registered as forwarder yet its message "
                    f"tried to be handler as if its from forwarder")
            raise StopPropagation

        if event.message.forward is not None:
            self.accumulate_forward(event=event)
            raise StopPropagation

        # parse message
        message_words = event.message.message.split(' ')

        if len(message_words) < 3:
            get_logger().error(
                msg=f"forwarder with user id={event.message.from_id} sent message id={event.message.id} of "
                    f"invalid format: {event.message.message}")
            raise StopPropagation

        forwarded_message_type = MessageType[message_words[0]]

        # branch on message type
        if forwarded_message_type == MessageType.MESSAGE:
            forwarded_username = message_words[1]
            forwarded_message_ids = [int(message_id) for message_id in message_words[2:]]

            # resolve chat from username
            forwarded_from_chat = await event.client.get_input_entity(forwarded_username)
            # have to use get_peer_id because entity by default has modified fake id
            forwarded_from_chat_id = await event.client.get_peer_id(forwarded_from_chat)

            await self.forward_messages(
                event=event,
                forwarded_message_type=forwarded_message_type,
                forwarded_from_chat_id=forwarded_from_chat_id,
                forwards_count=len(forwarded_message_ids),
                messages=forwarded_message_ids,
                from_peer=forwarded_from_chat)
        elif forwarded_message_type == MessageType.FORWARD_SOURCE:
            forwarded_from_chat_id = int(message_words[1])
            forwarded_message_hashes = [int(message_hash) for message_hash in message_words[2:]]

            # we should await until all these messages are received
            waits = 1
            while not all(msg_hash in self.forwards for msg_hash in forwarded_message_hashes):
                if self.max_wait_count < waits:
                    get_logger().error(f"Not all expected forwards from {forwarded_from_chat_id} were received in "
                                       f"{self.max_wait_count * self.timeout_seconds} seconds; stop waiting")
                    # erase all msg_hashes that are saved
                    self.erase_forwards(hashes=forwarded_message_hashes)

                    raise StopPropagation

                get_logger().debug(
                    f"waiting for all expected forwards to come wait#{waits} for {self.timeout_seconds}s")
                await sleep(self.timeout_seconds)
                waits += 1

            forwarded_messages = [self.take_first_forward(msg_hash=msg_hash) for msg_hash in forwarded_message_hashes]

            await self.forward_messages(
                event=event,
                forwarded_message_type=forwarded_message_type,
                forwarded_from_chat_id=forwarded_from_chat_id,
                forwards_count=len(forwarded_messages),
                messages=forwarded_messages)
        else:
            raise RuntimeError(f"Message type={forwarded_message_type.name} is not handled")

        raise StopPropagation
