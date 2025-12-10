import logging

from abc import ABC, abstractmethod
from typing import Optional


class ClientError(Exception):
    pass


class ClientInterface(ABC):
    def __init__(self, client_name: Optional[str] = None) -> None:
        super().__init__()

        self._client_name = self.__class__.__name__ if client_name is None else client_name
        self._log = logging.getLogger(f"ApiClient.{self._client_name}")

    def get(self, data):
        pass

    def put(self, data):
        pass

    def post(self, data):
        pass

    def delete(self, data):
        pass

    @property
    def client_name(self) -> str:
        return self._client_name
