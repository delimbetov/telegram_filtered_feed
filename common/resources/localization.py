from enum import Enum
from pathlib import Path
from pyjavaproperties import Properties
from common.logging import get_logger


# handlers
g_key_handlers_not_enrolled = "HANDLERS_NOT_ENROLLED"
g_key_handlers_failed_to_resolve = "HANDLERS_FAILED_TO_RESOLVE"
g_key_handlers_resolve_might_take_time = "HANDLERS_RESOLVE_MIGHT_TAKE_TIME"
g_key_handlers_no_username = "HANDLERS_NO_USERNAME"

# # help
g_key_handlers_help_0 = "HANDLERS_HELP_0"
g_key_handlers_help_1 = "HANDLERS_HELP_1"
g_key_handlers_help_2 = "HANDLERS_HELP_2"

# # list
g_key_handlers_list_count = "HANDLERS_LIST_COUNT"
g_key_handlers_list_list = "HANDLERS_LIST_LIST"

# # start
g_key_handlers_start_not_user = "HANDLERS_START_NOT_USER"
g_key_handlers_start_already_enabled = "HANDLERS_START_ALREADY_ENABLED"
g_key_handlers_start_already_existed = "HANDLERS_START_ALREADY_EXISTED"
g_key_handlers_start_introduction_0 = "HANDLERS_START_INTRODUCTION_0"
g_key_handlers_start_introduction_1 = "HANDLERS_START_INTRODUCTION_1"
g_key_handlers_start_introduction_2 = "HANDLERS_START_INTRODUCTION_2"
# # stop
g_key_handlers_stop_not_started = "HANDLERS_STOP_NOT_STARTED"
g_key_handlers_stop_did_stop = "HANDLERS_STOP_DID_STOP"
# # forwarded
g_key_handlers_forwarded_message_not_channel = "HANDLERS_FORWARDED_NOT_A_CHANNEL"
g_key_handlers_forwarded_message_not_public = "HANDLERS_FORWARDED_NOT_A_PUBLIC_CHANNEL"
# # follow
g_key_handlers_follow_unfollow_no_args = "HANDLERS_FOLLOW_UNFOLLOW_NO_ARGS"
g_key_handlers_follow_already_enabled = "HANDLERS_FOLLOW_ALREADY_ENABLED"
g_key_handlers_follow_did_enable = "HANDLERS_FOLLOW_DID_ENABLE"
# # unfollow
g_key_handlers_unfollow_not_followed = "HANDLERS_UNFOLLOW_NOT_FOLLOWED"
g_key_handlers_unfollow_did_disable = "HANDLERS_UNFOLLOW_DID_DISABLE"

g_ietf_russian = "ru"
g_ietf_english = "en"
g_strings = dict()


class Language(Enum):
    RUSSIAN = 0
    ENGLISH = 1

    def get_property_file_suffix(self):
        if self == Language.RUSSIAN:
            return "ru"
        elif self == Language.ENGLISH:
            return "en"

        raise RuntimeError("Unsupported language")


def get_language_from_ietf_code(ietf_language_code: str) -> Language:
    lang_code = str()

    if ietf_language_code is None:
        lang_code = g_ietf_english
        get_logger().warning(f"ietf language code is None; defaulted to {lang_code}")
    else:
        lang_code = ietf_language_code

    lowered = lang_code.lower()

    if lowered == g_ietf_russian:
        return Language.RUSSIAN
    elif lowered.startswith(g_ietf_english):
        return Language.ENGLISH

    # default to english
    get_logger().warning(f"Unknown language code={ietf_language_code}. Default to ENGLISH")
    return Language.ENGLISH


def get_localized(key: str, language: Language, values: list = None):
    base = g_strings[language.name][key]
    token = "VALUE"

    if values is not None and len(values) > 0:
        for idx, value in enumerate(values):
            base = base.replace(f"{token}{idx}", str(value))

    if token in base:
        raise RuntimeError(f"message key={key} expects more arguments")

    return base


def load_localizations():
    global g_strings

    for enum_value in Language:
        property_file_path = Path(__file__).with_name(
            f"strings_{enum_value.get_property_file_suffix()}").with_suffix(".properties")
        get_logger().info(f"Loading properties from file={property_file_path}")

        lang_properties = Properties()
        lang_properties.load(open(property_file_path))
        property_dict = lang_properties.getPropertyDict()

        # check all keys are there
        expected_keys = [globals()[key] for key in globals().keys() if key.startswith("g_key_")]
        if not all(key in property_dict for key in expected_keys):
            raise RuntimeError(f"Not all keys are in property dict={property_file_path}")

        # replace newline token with actual newline
        g_strings[enum_value.name] = {key: value.replace("NEWLINE", "\n") for key, value in property_dict.items()}
        get_logger().debug(f"Loaded properties for lang={enum_value.name}: {str(g_strings[enum_value.name])}")

