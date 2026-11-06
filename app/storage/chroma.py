"""ChromaDB access."""

from functools import cached_property

import chromadb
from chromadb.api import ClientAPI
from chromadb.config import Settings as ChromaClientSettings

from app.errors import ServiceUnavailableError


class ChromaServer:
    """Connects on first use, so that the application can start while ChromaDB is down."""

    def __init__(self, host: str, port: int) -> None:
        self.address = f"{host}:{port}"
        self._host = host
        self._port = port

    @cached_property
    def client(self) -> ClientAPI:
        try:
            return chromadb.HttpClient(
                host=self._host,
                port=self._port,
                settings=ChromaClientSettings(anonymized_telemetry=False),
            )
        except Exception as exc:  # the client raises bare ValueError or transport errors on a failed handshake
            raise ServiceUnavailableError(f"ChromaDB is not reachable at {self.address}: {exc}") from exc

    def version(self) -> str:
        try:
            return self.client.get_version()
        except ServiceUnavailableError:
            raise
        except Exception as exc:
            self.__dict__.pop("client", None)  # reconnect next time: the server may have restarted
            raise ServiceUnavailableError(f"ChromaDB is not reachable at {self.address}: {exc}") from exc
