from enum import Enum
from .pickle import PicklePersistentStorage
from .postgres import PostgresPersistentStorage


class PersistentStorageType(Enum):
    Pickle = 0
    Postgres = 1


class PostgresConfig:
    # pw is ok to be none
    def __init__(self, database: str, user: str, password: str, host: str, port: int):
        if len(database) < 1:
            raise RuntimeError("Invalid database: " + database)

        if len(user) < 1:
            raise RuntimeError("Invalid user: " + user)

        if len(host) < 1:
            raise RuntimeError("Invalid host: " + host)

        if port < 1:
            raise RuntimeError("Invalid port: " + str(port))

        # do not check pw as it might not be specified
        self.database = database
        self.user = user
        self.password = password
        self.host = host
        self.port = port

    def __repr__(self):
        return "database={}, user={}, pw=***, host={}, port={}".format(self.database, self.user, self.host, self.port)


class PersistenceConfig:
    def __init__(self, persistence_type: PersistentStorageType, **kwargs):
        if persistence_type == PersistentStorageType.Pickle:
            self.persistence_pickle_file_path = kwargs['persistence_pickle_file_path']

            if self.persistence_pickle_file_path is None or len(self.persistence_pickle_file_path) < 1:
                raise RuntimeError("Invalid persistence file path: " + self.persistence_pickle_file_path)
        elif persistence_type == PersistentStorageType.Postgres:
            self.postgres_config = kwargs['postgres_config']
        else:
            raise RuntimeError("Unknown persistence type: " + persistence_type.name)

        self.persistence_type = persistence_type

    def __repr__(self):
        return str(self.__dict__)


def create_persistent_storage(persistence_config: PersistenceConfig):
    if persistence_config.persistence_type == PersistentStorageType.Pickle:
        return PicklePersistentStorage(file_path=persistence_config.persistence_pickle_file_path)
    elif persistence_config.persistence_type == PersistentStorageType.Postgres:
        return PostgresPersistentStorage(**persistence_config.postgres_config.__dict__)

    raise RuntimeError("Unknown persistent storage type: " + str(type.name))