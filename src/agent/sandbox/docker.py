import os
import subprocess
import tempfile
import time
import uuid


class DockerSandbox:
    """Opt-in Linux container with no network or host writable mount.

    Docker is defense-in-depth, not sufficient for hostile multi-tenant workloads.
    The image must be provisioned by the operator; runtime never pulls it.
    """
    def __init__(self, image="python:3.11-slim", timeout=30):
        self.image, self.timeout = image, timeout

    def execute(self, code, workspace):
        name = "agent-" + uuid.uuid4().hex
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = ["docker", "run", "--rm", "--pull=never", "--log-driver=none", "--name", name,
                   "--network=none", "--read-only", "--cap-drop=ALL",
                   "--security-opt=no-new-privileges", "--memory=256m", "--cpus=1",
                   "--pids-limit=64", "--user=65534:65534", "--tmpfs=/tmp:rw,noexec,nosuid,size=32m",
                   "--mount", f"type=bind,source={workspace.root},target=/workspace,readonly",
                   "--workdir=/workspace", self.image, "python", "-I", "-c", code]
        # File-backed output avoids unbounded capture_output memory.
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, creationflags=flags)
            try:
                deadline = time.monotonic() + self.timeout
                while process.poll() is None:
                    if os.fstat(output.fileno()).st_size > 65536:
                        process.kill()
                        process.wait()
                        raise ValueError("Sandbox output limit exceeded")
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired(command, self.timeout)
                    time.sleep(0.05)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise TimeoutError("Sandbox execution timed out")
            finally:
                # Exact generated name; never touch other containers.
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=10, creationflags=flags)
            output.seek(0)
            data = output.read(65537)
            return {"exit_code": process.returncode, "output": data[:65536].decode("utf-8", errors="replace"),
                    "truncated": len(data) > 65536}
