import logging

import keyring
from yandex_music import Client

from .constants import APP_NAME

logger = logging.getLogger(__name__)


class TokenStore:
    def load(self) -> str | None:
        return keyring.get_password(APP_NAME, "token")

    def validate_and_save(self, token: str):
        logger.info("Account validation started")
        client = Client(token=token).init(timeout=5)
        logger.info("Account validated; saving credential")
        keyring.set_password(APP_NAME, "token", token)
        logger.info("Account credential saved")
        return client

    def delete(self) -> None:
        if self.load() is not None:
            keyring.delete_password(APP_NAME, "token")
