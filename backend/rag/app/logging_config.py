import logging
import sys


def setup_logging() -> logging.Logger:
    """
    Configure application logging.
    """

    logger = logging.getLogger("fundlens")

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


logger = setup_logging()