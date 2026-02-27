from abc import ABC, abstractmethod


class BaseAdapter(ABC):
    @abstractmethod
    def validate_config(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def fetch(self):
        raise NotImplementedError

    @abstractmethod
    def normalize(self, raw_data):
        raise NotImplementedError
