from pathlib import Path

from src.modules.iam.application.acl.ports.disposable_email_policy import (
    DisposableEmailPolicy,
)


class FileDisposableEmailPolicy(DisposableEmailPolicy):
    def __init__(self, path: Path | None = None) -> None:
        default_path = (
            Path(__file__).resolve().parent.parent / "resources" / "disposable_domains.txt"
        )
        file_path = path or default_path
        self._domains: frozenset[str] = frozenset(
            line.strip().lower()
            for line in file_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    def is_disposable(self, domain: str) -> bool:
        return domain.strip().lower() in self._domains
