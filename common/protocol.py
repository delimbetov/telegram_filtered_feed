from enum import Enum


g_resolver_response_error_prefix = "ERROR"
g_resolver_request_command = "/resolve"
g_resolver_separator = "\n"


class MessageType(Enum):
    MESSAGE = 0
    FORWARD_SOURCE = 1
