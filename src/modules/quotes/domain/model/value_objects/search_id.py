import re
import secrets
import time
from dataclasses import dataclass

from src.shared.domain.domain_error import DomainError

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_SEARCH_ID_RE = re.compile(r"^srch_[0-9A-HJKMNP-TV-Z]{26}$")


def _encode_base32(value: int, length: int) -> str:
    chars = ["0"] * length
    for idx in range(length - 1, -1, -1):
        chars[idx] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(chars)


@dataclass(frozen=True, slots=True)
class SearchId:
    value: str

    def __post_init__(self) -> None:
        if not _SEARCH_ID_RE.match(self.value):
            raise DomainError("SEARCH_NOT_FOUND", "Identificador de búsqueda inválido.")

    @staticmethod
    def generate() -> "SearchId":
        ms = int(time.time() * 1000) & ((1 << 48) - 1)
        rand80 = secrets.randbits(80)
        ulid_str = _encode_base32(ms, 10) + _encode_base32(rand80, 16)
        return SearchId(f"srch_{ulid_str}")
