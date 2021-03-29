from functools import wraps
from time import time, sleep
from typing import Optional
from logging import INFO
from itertools import chain
import psycopg2
import psycopg2.extensions
from aiopg import create_pool
from aiopg.transaction import IsolationLevel, Transaction
from asyncio import get_event_loop
from psycopg2.sql import SQL, Identifier
from common.logging import get_logger
from common.telegram import ChatType
from common.resources.localization import Language
from common.interval import MultiInterval, ContinuousInclusiveInterval
from .base import IPersistentStorage


# chats
g_chats = "chats"
g_chats_id = "id"
g_chats_telegram_chat_id = "telegram_chat_id"
g_chats_chat_type = "chat_type"
g_chats_telegram_chat_id_unique = "chats_telegram_chat_id_unique"

# user chats
g_user_chats = "user_chats"
g_user_chats_id = "id"
g_user_chats_chats_id = "chats_id"
g_user_chats_language = "language"
g_user_chats_enabled = "enabled"
g_user_chats_chats_id_unique = "user_chats_chats_id_unique"

# monitored chats
g_monitored_chats = "monitored_chats"
g_monitored_chats_id = "id"
g_monitored_chats_chats_id = "chats_id"
g_monitored_chats_title = "title"
g_monitored_chats_joiner = "joiner"
g_monitored_chats_enabled = "enabled"
g_monitored_chats_chats_id_unique = "monitored_chats_chats_id_unique"
g_monitored_chats_modification_time = "modification_time"

# subscriptions
g_subscriptions = "subscriptions"
g_subscriptions_id = "id"
g_subscriptions_user_chats_id = "user_chats_id"
g_subscriptions_monitored_chats_id = "monitored_chats_id"
g_subscriptions_enabled = "enabled"
g_subscriptions_user_monitored_chats_id_unique = "subscriptions_user_monitored_chats_is_unique"


def timed(log_level: int = INFO):
    def decorator(func):
        @wraps(func)
        async def wrap(*args, **kwargs):
            ts = time()
            result = await func(*args, **kwargs)
            duration = time() - ts
            get_logger().log(
                level=log_level,
                msg=f"func: {func.__name__}; duration: {str(duration)[:5]} sec; "
                    f"args: {str(args)}; kwargs: {str(kwargs)}")
            return result
        return wrap
    return decorator


def retriable_transaction(
        isolation_level: IsolationLevel = IsolationLevel.read_committed,
        readonly: bool = False,
        max_retries_count: int = 10,
        timeout_ms: int = 100):
    def decorator(transaction):
        @wraps(transaction)
        async def wrapper(*args, **kwargs):
            self = args[0]
            try_number = 0

            while try_number <= max_retries_count:
                if try_number > 0:
                    sleep(timeout_ms / 1000)
                    get_logger().warning(
                        f"Retrying transaction {transaction.__name__}: {try_number}/{max_retries_count}")

                try:
                    async with self.connection_pool.acquire() as connection:
                        async with connection.cursor() as cursor:
                            async with Transaction(
                                    cur=cursor,
                                    isolation_level=isolation_level,
                                    readonly=readonly) as scope_of_transaction:
                                get_logger().debug(
                                    f"Performing transaction {transaction.__name__} "
                                    f"args={str(args)} kwargs={str(kwargs)}")
                                kwargs['cursor'] = cursor
                                return await transaction(*args, **kwargs)
                except psycopg2.Warning as warning:
                    get_logger().warning(
                        "Warning while performing transaction {}: {}".format(
                            transaction.__name__, str(warning.__dict__)))
                    # TODO: warning should not force retry, but it being an exception does not allow to get result
                    # of the transaction
                except psycopg2.Error as error:
                    get_logger().error("Failed to perform transaction {}: code={}; error={}; diag={}".format(
                        transaction.__name__, error.pgcode, error.pgerror, str(error.diag)))

                try_number += 1

            raise RuntimeError(f"Failed to perform transaction {transaction.__name__}")
        return wrapper
    return decorator


@timed()
async def execute(cursor, query, values):
    get_logger().debug(f"Running query=\"{query}\" with values=\"{values}\" ...")
    await cursor.execute(operation=query, parameters=values)
    get_logger().debug(f"Finished {cursor.query}")


async def update_chat_type(cursor, chat_id: int, chat_type: ChatType):
    query = SQL("UPDATE {} SET {}=%s WHERE {}=%s").format(
        Identifier(g_chats),
        Identifier(g_chats_chat_type),
        Identifier(g_chats_telegram_chat_id))
    values = chat_type.value, chat_id
    await execute(cursor, query, values)

    # if we are updating chat type it must be there
    if cursor.rowcount != 1:
        raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")


async def update_title_joiner(cursor, chat_id: int, title: str, joiner: str):
    query = SQL("UPDATE {} SET {}=%s, {}=%s FROM {} WHERE {}=%s AND {}={}").format(
        Identifier(g_monitored_chats),
        # set
        Identifier(g_monitored_chats_title),
        Identifier(g_monitored_chats_joiner),
        # from
        Identifier(g_chats),
        # where
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_monitored_chats, g_monitored_chats_chats_id))
    values = title, joiner, chat_id
    await execute(cursor, query, values)

    # if we are updating chat type it must be there
    if cursor.rowcount != 1:
        raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")


async def get_user_chat_exists_enabled_type(cursor, chat_id: int, chat_type: ChatType = None):
    existed_before = False
    enabled_before = False
    language_before = None

    # check if chat is there and enabled
    query = SQL("SELECT {}, {}, {} FROM {}, {} WHERE {}=%s AND {}={}").format(
        Identifier(g_user_chats, g_user_chats_enabled),
        Identifier(g_chats, g_chats_chat_type),
        Identifier(g_user_chats, g_user_chats_language),
        Identifier(g_chats),
        Identifier(g_user_chats),
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_user_chats, g_user_chats_chats_id))
    values = chat_id,
    await execute(cursor, query, values)

    if cursor.rowcount > 1:
        raise RuntimeError(f"{cursor.query} returned unexpected amount of rows={cursor.rowcount}")
    elif cursor.rowcount == 1:
        existed_before = True
        result = await cursor.fetchone()
        get_logger().debug(f"{cursor.query} returned result={result}")

        if len(result) != 3 or not isinstance(result[0], bool) or not isinstance(result[1], int):
            raise RuntimeError(f"{cursor.query} returned invalid amount of columns or invalid result={result}")

        enabled_before = result[0]
        curr_chat_type = ChatType(value=result[1])
        language_before = Language(value=result[2])

        # should not happen
        if chat_type is not None and chat_type != curr_chat_type:
            get_logger().error(f"CHAT TYPE MISMATCH: old={curr_chat_type} new={chat_type}. Update to new one")
            await update_chat_type(cursor=cursor, chat_id=chat_id, chat_type=chat_type)
    else:
        get_logger().debug(f"There are no chats with chat_id={chat_id}")

    return existed_before, enabled_before, language_before


async def get_monitored_chat_exists_enabled(
        cursor, chat_id: int, chat_type: Optional[ChatType], title: Optional[str], joiner: Optional[str]):
    existed_before = False
    enabled_before = False
    title_after = None
    joiner_after = None

    # check if chat is there and enabled
    query = SQL("SELECT {}, {}, {}, {} FROM {}, {} WHERE {}=%s AND {}={}").format(
        Identifier(g_monitored_chats, g_monitored_chats_enabled),
        Identifier(g_chats, g_chats_chat_type),
        Identifier(g_monitored_chats, g_monitored_chats_title),
        Identifier(g_monitored_chats, g_monitored_chats_joiner),
        # from
        Identifier(g_chats),
        Identifier(g_monitored_chats),
        # where
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_monitored_chats, g_monitored_chats_chats_id))
    values = chat_id,
    await execute(cursor, query, values)

    if cursor.rowcount > 1:
        raise RuntimeError(f"{cursor.query} returned unexpected amount of rows={cursor.rowcount}")
    elif cursor.rowcount == 1:
        existed_before = True
        result = await cursor.fetchone()
        get_logger().debug(f"{cursor.query} returned result={result}")

        if len(result) != 4 or not isinstance(result[0], bool) or not isinstance(result[1], int)\
                or not isinstance(result[2], str) or not isinstance(result[3], str):
            raise RuntimeError(f"{cursor.query} returned invalid amount of columns or invalid result={result}")

        enabled_before = result[0]
        db_chat_type = ChatType(value=result[1])
        db_title = result[2]
        db_joiner = result[3]

        # check that either all are none or all have value
        are_nones = [chat_type is None, title is None, joiner is None]

        if len(set(are_nones)) != 1:
            raise RuntimeError("Args contract is broken not all are none and not all have value: ", are_nones)

        if are_nones[0] is False:
            # should not happen
            if chat_type != db_chat_type:
                get_logger().error(f"CHAT TYPE MISMATCH: old={db_chat_type} new={chat_type}. Update to new one")
                await update_chat_type(cursor=cursor, chat_id=chat_id, chat_type=chat_type)

            if title != db_title:
                get_logger().info(f"TITLE MISMATCH: old={db_title} new={title}. Update to new one")
                await update_title_joiner(cursor=cursor, chat_id=chat_id, title=title, joiner=joiner)
            elif joiner != db_joiner:
                # its elif because update_title_joiner would update joiner if title mismatches
                get_logger().info(f"JOINER MISMATCH: old={db_joiner} new={joiner}. Update to new one")
                await update_title_joiner(cursor=cursor, chat_id=chat_id, title=title, joiner=joiner)

            title_after = title
            joiner_after = joiner
        else:
            title_after = db_title
            joiner_after = db_joiner
    else:
        get_logger().debug(f"There are no chats with chat_id={chat_id}")

    return existed_before, enabled_before, title_after, joiner_after


# returns exists, enabled
async def get_subscription_exists_enabled(cursor, user_chat_id: int, monitored_chat_id: int):
    sql = SQL("SELECT {} FROM {} "
              "WHERE "
              "{}=(SELECT {} FROM {}, {} WHERE {}=%s AND {}={}) AND "
              "{}=(SELECT {} FROM {}, {} WHERE {}=%s AND {}={}) ")
    query = sql.format(
        Identifier(g_subscriptions_enabled),
        # from
        Identifier(g_subscriptions),
        # where user
        Identifier(g_subscriptions_user_chats_id),
        # select user chat
        Identifier(g_user_chats, g_user_chats_id),
        Identifier(g_user_chats),
        Identifier(g_chats),
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_user_chats, g_user_chats_chats_id),
        # where monitored
        Identifier(g_subscriptions_monitored_chats_id),
        # select monitored chat
        Identifier(g_monitored_chats, g_monitored_chats_id),
        Identifier(g_monitored_chats),
        Identifier(g_chats),
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_monitored_chats, g_monitored_chats_chats_id))
    values = user_chat_id, monitored_chat_id
    await execute(cursor, query, values)

    if cursor.rowcount == 0:
        return False, False
    elif cursor.rowcount > 1:
        raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")

    result = await cursor.fetchone()
    get_logger().debug(f"{cursor.query} returned result={result}")

    if len(result) != 1 or not isinstance(result[0], bool):
        raise RuntimeError(f"{cursor.query} returned invalid amount of columns or invalid result={result}")

    return True, result[0]


async def insert_new_chat(cursor, chat_id: int, chat_type: ChatType, existed_before: bool) -> bool:
    sql = SQL("INSERT INTO {} ({}, {}) VALUES (%s, %s) ON CONFLICT ON CONSTRAINT {} DO NOTHING;")
    query = sql.format(
        Identifier(g_chats),
        Identifier(g_chats_telegram_chat_id),
        Identifier(g_chats_chat_type),
        Identifier(g_chats_telegram_chat_id_unique))
    values = chat_id, chat_type.value
    await execute(cursor, query, values)

    # 0 if no chat before, 1 if it was there before, but never should there be > 1
    if cursor.rowcount > 1:
        raise RuntimeError(f"{cursor.query} inserted unexpected amount of rows={cursor.rowcount}")

    chat_inserted = cursor.rowcount == 1

    if existed_before == chat_inserted:
        if chat_inserted:
            get_logger().warning(f"For some reason chat id={chat_id} was reinserted although it was there already")
        else:
            raise RuntimeError(f"Failed to insert chat id={chat_id}")


async def insert_or_enable_user_chat(cursor, chat_id: int, language: Language):
    sql = SQL("INSERT INTO {} ({}, {})"
              " SELECT {}, %s FROM {} WHERE {}=%s"
              " ON CONFLICT ON CONSTRAINT {} DO UPDATE SET {}=TRUE")
    query = sql.format(
        Identifier(g_user_chats),
        Identifier(g_user_chats_chats_id),
        Identifier(g_user_chats_language),
        Identifier(g_chats, g_chats_id),
        Identifier(g_chats),
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_user_chats_chats_id_unique),
        Identifier(g_user_chats_enabled))
    values = language.value, chat_id
    await execute(cursor, query, values)

    # upsert returns 1 on insert and update. other numbers are failures
    if cursor.rowcount != 1:
        raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")

    # no adequate option to extract information on whether update OR insert took place TODO: see returning with join


async def insert_or_enable_monitored_chat(cursor, chat_id: int, title: str, joiner: str):
    sql = SQL("INSERT INTO {} ({}, {}, {})"
              " SELECT {}, %s, %s FROM {} WHERE {}=%s"
              " ON CONFLICT ON CONSTRAINT {} DO UPDATE SET {}=TRUE")
    query = sql.format(
        # insert
        Identifier(g_monitored_chats),
        Identifier(g_monitored_chats_chats_id),
        Identifier(g_monitored_chats_title),
        Identifier(g_monitored_chats_joiner),
        # select
        Identifier(g_chats, g_chats_id),
        Identifier(g_chats),
        Identifier(g_chats, g_chats_telegram_chat_id),
        # on conflict
        Identifier(g_monitored_chats_chats_id_unique),
        Identifier(g_monitored_chats_enabled))
    values = title, joiner, chat_id
    await execute(cursor, query, values)

    # upsert returns 1 on insert and update. other numbers are failures
    if cursor.rowcount != 1:
        raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")

    # no adequate option to extract information on whether update OR insert took place TODO: see returning with join


async def disable_monitored_chat(cursor, chat_id: int):
    sql = SQL("UPDATE {} SET {}=FALSE WHERE "
              "{}=(SELECT {} FROM {} WHERE {}=%s)")
    query = sql.format(
        Identifier(g_monitored_chats),
        Identifier(g_monitored_chats_enabled),
        Identifier(g_monitored_chats_chats_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_chats),
        Identifier(g_chats, g_chats_telegram_chat_id))
    values = chat_id,
    await execute(cursor, query, values)

    # update returns 1 on update. other numbers are failures
    if cursor.rowcount != 1:
        raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")


async def insert_or_enable_subscription(cursor, user_chat_id: int, monitored_chat_id: int):
    sql = SQL("INSERT INTO {} ({}, {})"
              " SELECT "
              " (SELECT {} FROM {}, {} WHERE {}=%s AND {}={}) user_chats_id,"
              " (SELECT {} FROM {}, {} WHERE {}=%s AND {}={}) monitored_chats_id "
              " ON CONFLICT ON CONSTRAINT {} DO UPDATE SET {}=TRUE")
    query = sql.format(
        Identifier(g_subscriptions),
        Identifier(g_subscriptions_user_chats_id),
        Identifier(g_subscriptions_monitored_chats_id),
        # select1
        Identifier(g_user_chats, g_user_chats_id),
        Identifier(g_user_chats),
        Identifier(g_chats),
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_user_chats, g_user_chats_chats_id),
        # select2
        Identifier(g_monitored_chats, g_monitored_chats_id),
        Identifier(g_monitored_chats),
        Identifier(g_chats),
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_monitored_chats, g_monitored_chats_chats_id),
        # conflict
        Identifier(g_subscriptions_user_monitored_chats_id_unique),
        Identifier(g_subscriptions_enabled))
    values = user_chat_id, monitored_chat_id
    await execute(cursor, query, values)

    # upsert returns 1 on insert and update. other numbers are failures
    if cursor.rowcount != 1:
        raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")

    # no adequate option to extract information on whether update OR insert took place TODO: see returning with join


async def add_or_enable_monitored_chat(cursor, chat_id: int, chat_type: ChatType, title: str, joiner: str):
    if chat_type != ChatType.CHANNEL:
        raise RuntimeError("Only channels are supported yet as monitored chats")

    # get exited/enabled status of monitored chat
    existed_before, enabled_before, _, _ = await get_monitored_chat_exists_enabled(
        cursor=cursor, chat_id=chat_id, chat_type=chat_type, title=title, joiner=joiner)

    # now that we have existed_before, enabled_before figured out decide what to do
    # if chat is there and enabled, do nothing
    if enabled_before:
        if not existed_before:
            raise RuntimeError(f"Monitored consistency error: enabled_before=true, yet existed_before={existed_before}")

        return existed_before, enabled_before

    # if its not there or not enabled, put it there
    # first add to chats table (which should be mostly immutable)
    await insert_new_chat(cursor=cursor, chat_id=chat_id, chat_type=chat_type, existed_before=existed_before)

    # now we've it in chats table so put it into monitored chats / or update if its there
    await insert_or_enable_monitored_chat(cursor=cursor, chat_id=chat_id, title=title, joiner=joiner)

    return existed_before, enabled_before


async def get_channel_subscribers_count(cursor, chat_id: int) -> int:
    sql = SQL("SELECT COUNT({}) FROM {} WHERE {}=True AND {}=(SELECT {} FROM {}, {} WHERE {}=%s AND {}={})")
    query = sql.format(
        Identifier(g_subscriptions, g_subscriptions_id),
        Identifier(g_subscriptions),
        # where
        Identifier(g_subscriptions, g_subscriptions_enabled),
        Identifier(g_subscriptions, g_subscriptions_monitored_chats_id),
        # select
        Identifier(g_monitored_chats, g_monitored_chats_id),
        Identifier(g_monitored_chats),
        Identifier(g_chats),
        Identifier(g_chats, g_chats_telegram_chat_id),
        Identifier(g_chats, g_chats_id),
        Identifier(g_monitored_chats, g_monitored_chats_chats_id))
    values = chat_id,
    await execute(cursor, query, values)

    if cursor.rowcount != 1:
        raise RuntimeError(f"{cursor.query} returned unexpected amount of rows={cursor.rowcount}")

    result = await cursor.fetchone()
    get_logger().debug(f"{cursor.query} returned result={result}")

    if len(result) != 1 or not isinstance(result[0], int):
        raise RuntimeError(f"{cursor.query} returned invalid amount of columns or invalid result={result}")

    sub_count = result[0]

    if sub_count < 0:
        raise RuntimeError(f"{cursor.query} returned invalid count of subs={sub_count} for chat id={chat_id}")

    return sub_count


async def get_max_monitored_modification_time(cursor):
    sql = SQL("SELECT MAX({})::text FROM {}")
    query = sql.format(
        Identifier(g_monitored_chats, g_monitored_chats_modification_time),
        Identifier(g_monitored_chats))
    await execute(cursor, query, tuple())

    if cursor.rowcount > 1:
        raise RuntimeError(f"{cursor.query} returned unexpected amount of rows={cursor.rowcount}")

    result = await cursor.fetchone()
    get_logger().debug(f"{cursor.query} returned result={result}")

    if len(result) != 1:
        raise RuntimeError(f"{cursor.query} returned invalid amount of columns")

    # rowcount == 1 yet result is None if table is empty
    if not result[0]:
        return None

    if not isinstance(result[0], str):
        raise RuntimeError(f"{cursor.query} returned invalid result={result}")

    return result[0]


class PostgresPersistentStorage(IPersistentStorage):
    def __init__(self, **kwargs):
        self.connection_pool = get_event_loop().run_until_complete(create_pool(**kwargs))

    # IPersistentStorage
    async def __aenter__(self):
        await self.connection_pool.__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.connection_pool.__aexit__(exc_type, exc_val, exc_tb)

    async def subscribe(self, notifies_to_handlers: dict):
        async with self.connection_pool.acquire() as connection:
            async with connection.cursor() as cur:
                for notify, _ in notifies_to_handlers.items():
                    get_logger().debug(f"Start listening to {notify}")
                    await cur.execute(f"LISTEN {notify}")

    async def listen(self, notifies_to_handlers: dict, should_run_func):
        if len(notifies_to_handlers) == 0:
            return

        async with self.connection_pool.acquire() as connection:
            while should_run_func():
                new_notification = await connection.notifies.get()
                get_logger().info(f"Received notification: f{new_notification.channel}")

                if new_notification.channel in notifies_to_handlers:
                    await notifies_to_handlers[new_notification.channel]()
                else:
                    get_logger().warning(f"No handlers for notification: f{new_notification.channel}")

    @retriable_transaction()
    async def get_user_enrolled_and_locale(self, user_chat_id: int, cursor) -> tuple:
        existed_before, enabled_before, language_before = await get_user_chat_exists_enabled_type(
            cursor=cursor, chat_id=user_chat_id)
        get_logger().debug(f"user chat={user_chat_id} existed_before={existed_before} enabled_before={enabled_before}")

        # return enabled_before as is_enrolled intentionally
        return enabled_before, language_before

    @retriable_transaction()
    async def get_user_chat_id_enabled_subscriptions(self, user_chat_id: int, cursor) -> list:
        sql = SQL("SELECT {}, {} "
                  "FROM {}, {}, {} "
                  "WHERE "
                  "{}=(SELECT {} FROM {}, {} WHERE {}=%s AND {}={}) AND "
                  "{}={} AND "
                  "{}={} AND "
                  "{}=TRUE")
        query = sql.format(
            Identifier(g_monitored_chats, g_monitored_chats_title),
            Identifier(g_chats, g_chats_telegram_chat_id),
            # from
            Identifier(g_monitored_chats),
            Identifier(g_subscriptions),
            Identifier(g_chats),
            # where user
            Identifier(g_subscriptions_user_chats_id),
            # select user chat
            Identifier(g_user_chats, g_user_chats_id),
            Identifier(g_user_chats),
            Identifier(g_chats),
            Identifier(g_chats, g_chats_telegram_chat_id),
            Identifier(g_chats, g_chats_id),
            Identifier(g_user_chats, g_user_chats_chats_id),
            # where join subscriptions&monitored_chats
            Identifier(g_subscriptions, g_subscriptions_monitored_chats_id),
            Identifier(g_monitored_chats, g_monitored_chats_id),
            # where join monitored chats & chats
            Identifier(g_monitored_chats, g_monitored_chats_chats_id),
            Identifier(g_chats, g_chats_id),
            # where enabled
            Identifier(g_subscriptions, g_subscriptions_enabled))
        values = user_chat_id,
        await execute(cursor, query, values)

        # fetch
        title_id_subs = list()

        while True:
            partial_result = await cursor.fetchmany()
            get_logger().debug(f"{cursor.query} returned result={partial_result}")

            if not partial_result:
                break

            for row in partial_result:
                if len(row) != 2 or not isinstance(row[0], str) or not isinstance(row[1], int):
                    raise RuntimeError(
                        f"{cursor.query} returned invalid amount of columns or invalid result={partial_result}")

                title_id_subs.append((row[0], row[1]))

        return title_id_subs

    @retriable_transaction(isolation_level=IsolationLevel.repeatable_read)
    async def add_or_enable_user_chat(self, chat_id: int, chat_type: ChatType, language: Language, cursor) -> tuple:
        if chat_type == ChatType.CHANNEL:
            raise RuntimeError("Channels are not supported yet as users")

        existed_before, enabled_before, language_before = await get_user_chat_exists_enabled_type(
            cursor=cursor, chat_id=chat_id, chat_type=chat_type)

        if language_before is not None and language_before != language:
            get_logger().warning(f"Language mismatch: db={language_before.name} msg={language.name}. Use db")
            language = language_before

        # now that we have existed_before, enabled_before figured out decide what to do
        # if chat is there and enabled, do nothing
        if enabled_before:
            if not existed_before or language_before is None:
                raise RuntimeError(f"User consistency error: enabled_before=true, yet existed_before={existed_before} "
                                   f"and language before={language_before if language_before is not None else 'none'}")

            return existed_before, enabled_before, language_before

        # if its not there or not enabled, put it there
        # first add to chats table (which should be mostly immutable)
        await insert_new_chat(
            cursor=cursor, chat_id=chat_id, chat_type=chat_type, existed_before=existed_before)

        # now we've it in chats table so put it into user chats / or update if its there
        await insert_or_enable_user_chat(cursor=cursor, chat_id=chat_id, language=language)

        return existed_before, enabled_before, language

    @retriable_transaction(isolation_level=IsolationLevel.repeatable_read)
    async def disable_user_chat(self, chat_id: int, cursor) -> bool:
        existed_before, enabled_before, language_before = await get_user_chat_exists_enabled_type(
            cursor=cursor, chat_id=chat_id)
        get_logger().debug(f"user chat={chat_id} existed_before={existed_before} enabled_before={enabled_before}")

        if enabled_before:
            # disable user chat
            sql = SQL("UPDATE {} SET {}=FALSE "
                      "FROM {} "
                      "WHERE {}={} AND {}=%s")
            query = sql.format(
                # update
                Identifier(g_user_chats),
                Identifier(g_user_chats_enabled),
                # from
                Identifier(g_chats),
                # where
                Identifier(g_chats, g_chats_id),
                Identifier(g_user_chats, g_user_chats_chats_id),
                Identifier(g_chats, g_chats_telegram_chat_id))
            values = chat_id,
            await execute(cursor, query, values)

            if cursor.rowcount != 1:
                raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")

        return enabled_before

    @retriable_transaction(isolation_level=IsolationLevel.serializable)
    async def add_or_enable_subscription(
            self, user_chat_id: int, target_chat_id: int, target_title: str, target_joiner: str, cursor) -> tuple:
        # add or enable monitored chat
        monitored_existed_before, monitored_enabled_before = await add_or_enable_monitored_chat(
            cursor=cursor, chat_id=target_chat_id, chat_type=ChatType.CHANNEL, title=target_title, joiner=target_joiner)
        get_logger().debug(f"chat id in monitored_chats existed_before={monitored_existed_before} "
                           f"enabled_before={monitored_enabled_before}")

        # if it wasnt enabled before, send notify (it wont be delivered unless transaction is commited)
        subscription_existed_before, subscription_enabled_before = await get_subscription_exists_enabled(
            cursor=cursor, user_chat_id=user_chat_id, monitored_chat_id=target_chat_id)

        # now that we have existed_before, enabled_before figured out decide what to do
        # if subscription is there and enabled, do nothing
        if subscription_enabled_before:
            if not subscription_existed_before:
                raise RuntimeError(f"Subscription consistency error: enabled_before=true, "
                                   f"yet existed_before={subscription_existed_before}")

            return subscription_existed_before, subscription_enabled_before

        # if its not there or not enabled, put or enable it there
        await insert_or_enable_subscription(cursor=cursor, user_chat_id=user_chat_id, monitored_chat_id=target_chat_id)

        return subscription_existed_before, subscription_enabled_before

    @retriable_transaction(isolation_level=IsolationLevel.repeatable_read)
    async def get_all_user_chats(self, cursor) -> set:
        query = SQL("SELECT {}, {}, {}, {} FROM {}, {} WHERE {}={}").format(
            # select
            Identifier(g_user_chats, g_user_chats_enabled),
            Identifier(g_chats, g_chats_chat_type),
            Identifier(g_user_chats, g_user_chats_language),
            Identifier(g_chats, g_chats_telegram_chat_id),
            # from
            Identifier(g_chats),
            Identifier(g_user_chats),
            # where
            Identifier(g_chats, g_chats_id),
            Identifier(g_user_chats, g_user_chats_chats_id))
        await execute(cursor, query, tuple())

        # fetch
        user_chats = set()

        while True:
            partial_result = await cursor.fetchmany()
            get_logger().debug(f"{cursor.query} returned result={partial_result}")

            if not partial_result:
                break

            for row_result in partial_result:
                if len(row_result) != 4 or not isinstance(row_result[0], bool)\
                        or not isinstance(row_result[1], int) or not isinstance(row_result[2], int) \
                        or not isinstance(row_result[3], int):
                    raise RuntimeError(f"{cursor.query} returned invalid amount of columns "
                                       f"or invalid result={row_result}")

                user_chats.add((row_result[0], row_result[1], Language(value=row_result[2]), row_result[3]))

        return user_chats

    # TODO: its serializable because of sub count check. refactor it in the future (its definitely not a bottleneck atm)
    @retriable_transaction(isolation_level=IsolationLevel.serializable)
    async def disable_subscription(self, user_chat_id: int, target_chat_id: int, cursor) -> tuple:
        sql = SQL("UPDATE {} new_table SET {}=FALSE "
                  "FROM {} old_table "
                  "WHERE new_table.{}=old_table.{} AND "
                  "new_table.{}=(SELECT {} FROM {}, {} WHERE {}=%s AND {}={}) AND "
                  "new_table.{}=(SELECT {} FROM {}, {} WHERE {}=%s AND {}={}) "
                  "RETURNING old_table.{}")
        query = sql.format(
            Identifier(g_subscriptions),
            Identifier(g_subscriptions_enabled),
            # from
            Identifier(g_subscriptions),
            # where join
            Identifier(g_subscriptions_id),
            Identifier(g_subscriptions_id),
            # where user
            Identifier(g_subscriptions_user_chats_id),
            # select user chat
            Identifier(g_user_chats, g_user_chats_id),
            Identifier(g_user_chats),
            Identifier(g_chats),
            Identifier(g_chats, g_chats_telegram_chat_id),
            Identifier(g_chats, g_chats_id),
            Identifier(g_user_chats, g_user_chats_chats_id),
            # where monitored
            Identifier(g_subscriptions_monitored_chats_id),
            # select monitored chat
            Identifier(g_monitored_chats, g_monitored_chats_id),
            Identifier(g_monitored_chats),
            Identifier(g_chats),
            Identifier(g_chats, g_chats_telegram_chat_id),
            Identifier(g_chats, g_chats_id),
            Identifier(g_monitored_chats, g_monitored_chats_chats_id),
            # returning
            Identifier(g_subscriptions_enabled))
        values = user_chat_id, target_chat_id
        await execute(cursor, query, values)

        # 0 rows is lack of such subscription
        if cursor.rowcount == 0:
            return False, False, None, None
        elif cursor.rowcount > 1:
            raise RuntimeError(f"{cursor.query} affected unexpected amount of rows={cursor.rowcount}")
        else:
            # get old enabled value
            result = await cursor.fetchone()
            get_logger().debug(f"{cursor.query} returned result={result}")

            if len(result) != 1 or not isinstance(result[0], bool):
                raise RuntimeError(f"{cursor.query} returned invalid amount of columns or invalid result={result}")

            enabled_before = result[0]

            # disable monitored chat if its last subscription on that channel
            sub_count = await get_channel_subscribers_count(cursor=cursor, chat_id=target_chat_id)
            get_logger().debug(f"monitored chat id={target_chat_id} has sub count "
                               f"after disabling user chat id={user_chat_id}: {sub_count}")

            if sub_count < 1:
                get_logger().info(f"disabling monitoring of chat id={target_chat_id}")
                await disable_monitored_chat(cursor=cursor, chat_id=target_chat_id)

            # get db title
            _, _, title, joiner = await get_monitored_chat_exists_enabled(
                cursor=cursor, chat_id=target_chat_id, chat_type=None, title=None, joiner=None)

            if title is None or joiner is None:
                raise RuntimeError(f"Inconsistent db: title or joiner is none for monitored_chat_id={target_chat_id}")

            return enabled_before, True, title, joiner

    @retriable_transaction()
    async def get_channel_subscribers(self, chat_id, cursor) -> set:
        sql = SQL("SELECT {} FROM {}, {}, {} "
                  "WHERE "
                  "{}={} AND {}=TRUE AND "
                  "{}={} AND {}=TRUE AND "
                  "{}=(SELECT {} FROM {}, {} WHERE {}=%s AND {}={} AND {}=TRUE) ")
        query = sql.format(
            # select chats.telegram_chat_id
            Identifier(g_chats, g_chats_telegram_chat_id),
            # from chats & user_chats & subscriptions
            Identifier(g_chats),
            Identifier(g_user_chats),
            Identifier(g_subscriptions),
            # where user_chats.chats_id = chats.id
            Identifier(g_user_chats, g_user_chats_chats_id),
            Identifier(g_chats, g_chats_id),
            Identifier(g_user_chats, g_user_chats_enabled),
            # where subscriptions.user_chats_id=user_chats.id
            Identifier(g_subscriptions, g_subscriptions_user_chats_id),
            Identifier(g_user_chats, g_user_chats_id),
            Identifier(g_subscriptions, g_subscriptions_enabled),
            # where monitored
            Identifier(g_subscriptions, g_subscriptions_monitored_chats_id),
            # select monitored chat
            Identifier(g_monitored_chats, g_monitored_chats_id),
            Identifier(g_monitored_chats),
            Identifier(g_chats),
            Identifier(g_chats, g_chats_telegram_chat_id),
            Identifier(g_chats, g_chats_id),
            Identifier(g_monitored_chats, g_monitored_chats_chats_id),
            Identifier(g_monitored_chats, g_monitored_chats_enabled))
        values = chat_id,
        await execute(cursor, query, values)

        # fetch
        subbed_telegram_user_chat_ids = set()

        while True:
            partial_result = await cursor.fetchmany()
            get_logger().debug(f"{cursor.query} returned result={partial_result}")

            if not partial_result:
                break

            for row in partial_result:
                if len(row) != 1 or not isinstance(row[0], int):
                    raise RuntimeError(
                        f"{cursor.query} returned invalid amount of columns or invalid result={partial_result}")

                subbed_telegram_user_chat_ids.add(row[0])

        return subbed_telegram_user_chat_ids

    @retriable_transaction(isolation_level=IsolationLevel.repeatable_read)
    async def get_monitored_channels_delta(
            self,
            handicap_seconds: int,
            prev_max_time: str,
            monitored_chats_id_interval: MultiInterval,
            cursor) -> tuple:
        if prev_max_time is None:
            prev_max_time = '2000-01-01 19:10:25-07'

        where_interval_clause = "("

        for idx, interval in enumerate(monitored_chats_id_interval.intervals):
            if idx > 0:
                where_interval_clause += " OR "
            where_interval_clause += "{} BETWEEN %s AND %s"

        where_interval_clause += ")"
        unformatted_query_str = "SELECT {}, {}, {} " \
                                "FROM {}, {} " \
                                "WHERE {}={} AND {} > LEAST(%s::timestamp, NOW() - '%s seconds'::interval) AND "\
                                + where_interval_clause
        sql = SQL(unformatted_query_str)
        query = sql.format(
            # select
            Identifier(g_chats, g_chats_telegram_chat_id),
            Identifier(g_monitored_chats, g_monitored_chats_enabled),
            Identifier(g_monitored_chats, g_monitored_chats_joiner),
            # from
            Identifier(g_chats),
            Identifier(g_monitored_chats),
            # where
            Identifier(g_chats, g_chats_id),
            Identifier(g_monitored_chats, g_monitored_chats_chats_id),
            Identifier(g_monitored_chats, g_monitored_chats_modification_time),
            *[Identifier(g_monitored_chats, g_monitored_chats_id)
              for _ in range(len(monitored_chats_id_interval.intervals))])
        list_of_interval_pairs = [(interval.start, interval.end) for interval in monitored_chats_id_interval.intervals]
        # using chain to squash list of tuples into list of values of tuples
        values = prev_max_time, handicap_seconds, *list(chain(*list_of_interval_pairs))
        await execute(cursor, query, values)

        # fetch
        chat_to_enabled_dict = dict()

        while True:
            partial_result = await cursor.fetchmany()
            get_logger().debug(f"{cursor.query} returned result={partial_result}")

            if not partial_result:
                break

            for row in partial_result:
                if len(row) != 3 or not isinstance(row[0], int) or not isinstance(row[1], bool) \
                        or not isinstance(row[2], str):
                    raise RuntimeError(
                        f"{cursor.query} returned invalid amount of columns or invalid result={partial_result}")

                chat_to_enabled_dict[row[0]] = row[1], row[2]

        # get new max time
        new_max_time = await get_max_monitored_modification_time(cursor)

        return chat_to_enabled_dict, new_max_time
