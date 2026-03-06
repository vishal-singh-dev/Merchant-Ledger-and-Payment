from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class BrokerMessage:
    key: str
    value: dict
    headers: dict
    raw: object | None = None


class BrokerPublisher(ABC):
    @abstractmethod
    def publish(self, key: str, value: dict, headers: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    def publish_dlq(self, key: str, value: dict, headers: dict, error: str) -> None:
        raise NotImplementedError


class BrokerConsumer(ABC):
    @abstractmethod
    def poll(self, timeout: float = 1.0) -> list[BrokerMessage]:
        raise NotImplementedError

    @abstractmethod
    def ack(self, message: BrokerMessage) -> None:
        raise NotImplementedError
