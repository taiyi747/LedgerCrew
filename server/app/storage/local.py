from pathlib import Path, PurePosixPath

from app.core.config import get_settings


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        relative = PurePosixPath(key)
        if relative.is_absolute() or not relative.parts or any(part in {".", ".."} for part in relative.parts):
            raise ValueError("Unsafe storage key")
        path = self.root.joinpath(*relative.parts).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Unsafe storage key")
        return path

    def put(self, key: str, content: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(content)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_root)
