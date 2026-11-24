import json
import logging
import logging.config  # gives dictConfig()
from contextvars import ContextVar

# ContextVar creates a var whose value is specific to the current execution context
request_id_var = ContextVar("request_id", default="-")


class JSONFormatter(logging.Formatter):
    def format(self, record):  # extra fields from record
        level = record.levelname
        logger = record.name
        msg = record.getMessage()  # gives the final formatted message, with the arguments substitued.Hence, use this instead of record.msg
        request_id = request_id_var.get()

        standard_attrs = set(logging.makeLogRecord({}).__dict__)

        extras = {k: v for k, v in record.__dict__.items() if k not in standard_attrs}

        logging_dict = {
            "level": level,
            "logger": logger,
            "msg": msg,
            "request_id": request_id,
            "extras": extras,
        }

        return json.dumps(logging_dict)  # converts dict into json string


def setup_logging():
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        # how the logs look
        "formatters": {
            "json": {
                "()": JSONFormatter  # () tells configDict() which formatter class to instantiate
            }
        },
        # where the logs appear
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",  # sends logs to stream
                "stream": "ext://sys.stdout",  # sys.stdout means standard output(terminal)
                "formatter": "json",
            }
        },
        "root": {
            "level": "INFO",  # so even logger.info() gets printed, by default WARNING is the level, so it wasn't getting printed
            "handlers": ["console"],
        },
    }
    logging.config.dictConfig(config)
