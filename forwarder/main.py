from common.logging import configure_logging
from forwarder import Forwarder, ForwarderConfig, PersistenceConfig
from common.persistent_storage.factory import PostgresConfig, PersistentStorageType
from common.interval import ContinuousInclusiveInterval, MultiInterval
import config
import sys


def main():
    # Configure logging
    configure_logging(name="forwarder")

    # Parse command line args
    if len(sys.argv) < 5:
        raise RuntimeError("App id, app hash, and at least one interval are required to be passed as command line "
                           "argument")

    api_id = int(sys.argv[1])
    api_hash = sys.argv[2]

    if len(sys.argv) % 2 == 0:
        raise RuntimeError("Invalid intervals arguments")

    curr_idx = 3
    intervals = []

    while curr_idx < len(sys.argv):
        start = int(sys.argv[curr_idx])
        end = int(sys.argv[curr_idx + 1])
        curr_idx += 2
        intervals.append(ContinuousInclusiveInterval(start=start, end=end))

    multi_interval = MultiInterval(intervals=intervals)

    # Load configs
    postgres_config = PostgresConfig(
        database=config.db_name,
        user=config.db_user,
        password=config.db_password,
        host=config.db_host,
        port=config.db_port)
    persistence_type = \
        PersistentStorageType.Postgres if config.persistence_use_postgres else PersistentStorageType.Pickle
    persistence_config = PersistenceConfig(
        persistence_type=persistence_type,
        postgres_config=postgres_config,
        persistence_pickle_file_path=None)
    forwarder_config = ForwarderConfig(
        api_id=api_id,
        api_hash=api_hash,
        monitored_chats_id_interval=multi_interval,
        persistence_config=persistence_config,
        feedbot_username=config.feedbot_username,
        modification_time_handicap_seconds=config.modification_time_handicap_seconds,
        validation_hour=config.validation_hour,
        album_timeout_seconds=config.album_timeout_seconds)

    # Create forwarder obj
    forwarder = Forwarder(config=forwarder_config)

    # Run the forwarder
    forwarder.run()


if __name__ == '__main__':
    main()
