from pathlib import Path

from agent_framework import FileCheckpointStorage

from . import contracts


def create_checkpoint_storage(path: Path) -> FileCheckpointStorage:
    """Only this module's explicitly defined data models may be restored."""
    allowed = [
        f"{cls.__module__}:{cls.__qualname__}"
        for cls in vars(contracts).values()
        if isinstance(cls, type)
        and issubclass(cls, contracts.DataModel)
        and cls.__module__ == contracts.__name__
    ]
    return FileCheckpointStorage(path, allowed_checkpoint_types=allowed)
