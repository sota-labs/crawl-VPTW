from typing import Type, TypeVar

T = TypeVar("T")


def collection(name: str):
    def decorator(cls: Type[T]) -> Type[T]:
        setattr(cls, "__collection__", name)
        return cls

    return decorator
