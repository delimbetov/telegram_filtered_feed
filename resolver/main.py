from common.logging import configure_logging
from resolver import Resolver, ResolverConfig
import config
import sys


def main():
    # Configure logging
    configure_logging(name="resolver")

    # Parse command line args
    if len(sys.argv) != 3:
        raise RuntimeError("App id, app hash are required to be passed as command line argument")

    api_id = int(sys.argv[1])
    api_hash = sys.argv[2]
    join_tries = config.join_tries
    from_usernames = config.from_usernames

    # Load configs
    resolver_config = ResolverConfig(
        api_id=api_id,
        api_hash=api_hash,
        join_tries=join_tries,
        from_usernames=from_usernames)

    # Create resolver obj
    resolver = Resolver(config=resolver_config)

    # Run the forwarder
    resolver.run()


if __name__ == '__main__':
    main()
