import re
from pathlib import Path


class Workspace:
    def __init__(self, root: Path, session_id: str):
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise ValueError("Invalid workspace ID")
        self.root = Path(root).resolve() / session_id
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str):
        if not relative or Path(relative).is_absolute() or ":" in relative or "\\" in relative:
            raise PermissionError("Only workspace-relative POSIX paths are accepted")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise PermissionError("Path escapes workspace")
        return path
