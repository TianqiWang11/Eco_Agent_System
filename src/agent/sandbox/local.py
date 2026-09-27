from .workspace import Workspace


class LocalSandbox:
    """Trusted file adapter, NOT an OS security boundary. No host code execution."""
    def execute(self, code: str, workspace: Workspace):
        raise PermissionError("LocalSandbox cannot execute generated code; enable DockerSandbox")

    def read(self, path: str, workspace: Workspace):
        target = workspace.resolve(path)
        with target.open("rb") as stream:
            data = stream.read(65537)
        if len(data) > 65536:
            raise ValueError("File exceeds 64 KiB read limit")
        return {"text": data.decode("utf-8"), "path": path}

    def write(self, path: str, text: str, workspace: Workspace):
        if len(text.encode("utf-8")) > 65536:
            raise ValueError("File exceeds 64 KiB write limit")
        target = workspace.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # No silent overwrite. Files written by tools are session-local only.
        with target.open("x", encoding="utf-8") as stream:
            stream.write(text)
        return {"path": path, "created": True}
