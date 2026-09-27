from typing import Protocol
from .workspace import Workspace


class SandboxInterface(Protocol):
    def execute(self, code: str, workspace: Workspace) -> dict: ...
