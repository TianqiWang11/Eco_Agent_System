from urllib.parse import urlsplit


class Policy:
    def __init__(self, allowed_endpoints=()):
        self.allowed_endpoints = set(allowed_endpoints)

    def network(self, url: str):
        p = urlsplit(url)
        if (p.scheme not in {"http", "https"} or p.username or p.password or p.fragment
                or url not in self.allowed_endpoints):
            raise PermissionError("Network endpoint is not allowed")

    def approval_required(self, tool):
        return tool.approval
