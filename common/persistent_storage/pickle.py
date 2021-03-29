from .base import IPersistentStorage
import pickle
from common.logging import get_logger


g_storage_key_monitored_channels = 'monitored_channels'
g_storage_key_users_data = 'users_data'
g_storage_key_users_data_subscriptions = 'subscriptions'
g_storage_key_channels_data = 'channels_data'
g_storage_key_channels_data_subscribers = "subscribers"


# TODO: make thread safe
class PicklePersistentStorage(IPersistentStorage):
    # IPersistentStorage
    def sync(self):
        self.dump()

    def is_channel_monitored(self, chat_id) -> bool:
        is_monitored = chat_id in self.data[g_storage_key_monitored_channels]
        get_logger().debug(msg="channel with id={} is monitored {}".format(chat_id, is_monitored))

        return is_monitored

    def monitor_channel(self, chat_id):
        if chat_id in self.data[g_storage_key_monitored_channels]:
            get_logger().warning(msg="channel with id={} is already monitored".format(chat_id))

        get_logger().info(msg="channel with id={} is monitored now".format(chat_id))
        self.data[g_storage_key_monitored_channels].add(chat_id)

    def stop_monitoring_channel(self, chat_id):
        if chat_id not in self.data[g_storage_key_monitored_channels]:
            get_logger().warning(msg="channel with id={} is not monitored yet stop is requested".format(chat_id))
            return

        get_logger().info(msg="channel with id={} is not monitored now".format(chat_id))
        self.data[g_storage_key_monitored_channels].remove(chat_id)

    def add_user(self, user_id):
        if user_id in self.data[g_storage_key_users_data]:
            get_logger().warning(msg="user with id={} is already added".format(user_id))

        get_logger().info(msg="adding user with id={}".format(user_id))
        self.data[g_storage_key_users_data][user_id] = dict()
        
    def is_user_chat_subbed(self, user_chat_id, chat_id) -> bool:
        if user_id not in self.data[g_storage_key_users_data]:
            raise RuntimeError("is_user_chat_subbed is requested for missing user_id={}".format(user_id))

        is_subbed = chat_id in self.data[g_storage_key_users_data][user_id][g_storage_key_users_data_subscriptions]
        get_logger().debug(msg="user with id={} is subbed= to channel with id={}".format(user_id, is_subbed, chat_id))

        return is_subbed

    def subscribe_user_to(self, user_id, chat_id):
        if user_id not in self.data[g_storage_key_users_data]:
            raise RuntimeError("subscribe_user_to is requested for missing user_id={}".format(user_id))

        if chat_id in self.data[g_storage_key_users_data][user_id][g_storage_key_users_data_subscriptions]:
            get_logger().warning(msg="channel with id={} is already subscription of user_id=".format(chat_id, user_id))

        get_logger().info(msg="subbing user with id={} to channel with id=".format(user_id, chat_id))
        self.data[g_storage_key_users_data][user_id][g_storage_key_users_data_subscriptions].add(chat_id)

    def unsubscribe_user_from(self, user_id, chat_id):
        if user_id not in self.data[g_storage_key_users_data]:
            raise RuntimeError("subscribe_user_to is requested for missing user_id={}".format(user_id))

        if chat_id not in self.data[g_storage_key_users_data][user_id][g_storage_key_users_data_subscriptions]:
            get_logger().warning(
                msg="channel with id={} is not subscription of user_id={} yet unsubscribe is requested".format(
                    chat_id,
                    user_id))
            return

        self.data[g_storage_key_users_data][user_id][g_storage_key_users_data_subscriptions].remove(chat_id)

    # most load is gonna be here
    def get_channel_subscribers(self, chat_id) -> set:
        if chat_id not in self.data[g_storage_key_channels_data]:
            raise RuntimeError("get_channel_subscribers is requested for missing chat_id={}".format(chat_id))

        return self.data[g_storage_key_channels_data][chat_id][g_storage_key_channels_data_subscribers]

    def add_channel_subscriber(self, chat_id, user_id):
        if chat_id not in self.data[g_storage_key_channels_data]:
            raise RuntimeError("get_channel_subscribers is requested for missing chat_id={}".format(chat_id))

        if user_id in self.data[g_storage_key_channels_data][chat_id][g_storage_key_channels_data_subscribers]:
            get_logger().warning("adding already added user_id={} to chat_id={} subs".format(user_id, chat_id))

        self.data[g_storage_key_channels_data][chat_id][g_storage_key_channels_data_subscribers].add(user_id)

    def drop_channel_subscriber(self, chat_id, user_id):
        if chat_id not in self.data[g_storage_key_channels_data]:
            raise RuntimeError("get_channel_subscribers is requested for missing chat_id={}".format(chat_id))

        if user_id not in self.data[g_storage_key_channels_data][chat_id][g_storage_key_channels_data_subscribers]:
            get_logger().warning("removing missing user_id={} from chat_id={} subs".format(user_id, chat_id))
            return

        self.data[g_storage_key_channels_data][chat_id][g_storage_key_channels_data_subscribers].remove(user_id)

    # init/deinit
    def __init__(self, file_path: str):
        if file_path is None or len(file_path) < 1:
            raise RuntimeError("Invalid file_path for pickle pers storage")

        self.file_path = file_path
        self.load()

        if self.data is None or not isinstance(self.data, dict):
            raise RuntimeError("Failed to load pickle file")

    # destructor
    def __del__(self):
        self.dump()

    # Internal helpers
    def load(self):
        try:
            with open(self.file_path, "rb") as f:
                self.data = pickle.load(f)
        except IOError:
            # assuming IOError means there's no such file
            self.data = {
                g_storage_key_monitored_channels: set(),
                g_storage_key_users_data: dict(),
                g_storage_key_channels_data: dict()
            }
            # dump to assert file_path correctness
            self.dump()
        except pickle.UnpicklingError:
            raise TypeError("File {} does not contain valid pickle data".format(self.file_path))
        except Exception:
            raise TypeError("Something went wrong unpickling {}".format(self.file_path))

    def dump(self):
        with open(self.file_path, "wb") as f:
            pickle.dump(self.data, f)
