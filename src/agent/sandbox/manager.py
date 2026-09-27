from .workspace import Workspace
from .local import LocalSandbox
from .docker import DockerSandbox


class SandboxManager:
    def __init__(self, root, docker_enabled=False, image="python:3.11-slim"):
        self.root = root
        self.local = LocalSandbox()
        self.docker = DockerSandbox(image) if docker_enabled else None

    def workspace(self, session_id):
        return Workspace(self.root, session_id)

    def execute(self, code, session_id):
        if self.docker is None:
            raise PermissionError("DockerSandbox is disabled; host execution is forbidden")
        return self.docker.execute(code, self.workspace(session_id))
