# Abstract Base Class- a blueprint for other classes
# Abstract class is one that has various abstract methods, method declaration but no implementation
# module abc (Abstract base Class)
# An interface is a contact between a class and it's users, it specifies a set of methods that a class must use to be compatible with the interface
# don't explicitly inherit from the interface,instead we provide implementation of method.
# duck typing, meaning a class can inherit from an interface as long as it provides the req methods
from abc import ABC, abstractmethod


class BaseEmbedder(ABC):
    @abstractmethod
    async def embed_documents(self, texts: list[str], is_query: bool) -> list[list[float]]:
        pass
