import logging


g_logger = None


def get_logger():
    return g_logger


def configure_logging(name: str, level: int = logging.DEBUG):
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=level)
    global g_logger
    g_logger = logging.getLogger(name=name)
    g_logger.debug("logger with name=\"{}\" configured, min severity={}".format(name, logging.getLevelName(level)))
