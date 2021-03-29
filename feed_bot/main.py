from common.logging import configure_logging
from common.resources.localization import load_localizations
from bot import Bot, BotConfig, PersistenceConfig
from common.persistent_storage.factory import PostgresConfig, PersistentStorageType
import config
import sys


def main():
    # Configure logging
    configure_logging(name="feed_bot")

    # Parse command line args
    # 0 - prog name
    # 1 - api id
    # 2 - api hash
    # 3 - bot token
    # 4 - dev key
    # 5 - resolver username
    # >=6 - forwarders user ids
    if len(sys.argv) < 7:
        raise RuntimeError("App id, app hash, token, dev key, resolver username and forwarders user ids "
                           "are required to be passed as command line argument")

    api_id = int(sys.argv[1])
    api_hash = sys.argv[2]
    token = sys.argv[3]
    dev_key = sys.argv[4]
    # accepting single resolver arg for now, but it should be easy to scale in the future because everything else
    # is prepared for multi resolvers
    resolver_usernames = [sys.argv[5]]
    forwarders_user_ids = {int(arg) for arg in sys.argv[6:]}

    # Load localizations
    load_localizations()

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
        postgres_config=postgres_config)
    bot_config = BotConfig(
        api_id=api_id,
        api_hash=api_hash,
        token=token,
        dev_key=dev_key,
        resolver_usernames=resolver_usernames,
        forwarders_user_ids=forwarders_user_ids,
        resolve_max_wait_count=config.resolve_max_wait_count,
        resolve_timeout_seconds=config.resolve_timeout_seconds,
        resolve_warning_wait_number=config.resolve_warning_wait_number,
        forward_max_wait_count=config.forward_max_wait_count,
        forward_timeout_seconds=config.forward_timeout_seconds,
        persistence_config=persistence_config)

    # Create bot obj
    bot = Bot(config=bot_config)

    # Run the bot
    bot.run()


if __name__ == '__main__':
    main()
