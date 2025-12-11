from __future__ import annotations


class ValidEncoding:
    """Class to represent valid encodings."""

    def __init__(self, value: str | list[str], target_encoding: str) -> None:
        self.value = value
        self.target_encoding = target_encoding

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"ValidEncoding({self.value!r}, {self.target_encoding!r})"

    def values(self) -> list[str]:
        if isinstance(self.value, str):
            return [self.value]
        else:
            return self.value


_supported_encodings = {
    "utf8": ValidEncoding(["utf8", "utf-8"], "utf8"),
    "utf8-lossy": ValidEncoding(["utf8-lossy", "utf-8-lossy"], "utf8-lossy"),
    "ascii": ValidEncoding(["ascii"], "ascii"),
    "cp1252": ValidEncoding(["cp1252", "windows-1252"], "cp1252"),
    "cp850": ValidEncoding(["cp850", "dos-850"], "cp850"),
    "cp437": ValidEncoding(["cp437", "dos-437"], "cp437"),
    "cp852": ValidEncoding(["cp852", "dos-852"], "cp852"),
    "cp866": ValidEncoding(["cp866", "dos-866"], "cp866"),
    "cp865": ValidEncoding(["cp865", "dos-865"], "cp865"),
    "cp861": ValidEncoding(["cp861", "dos-861"], "cp861"),
    "cp874": ValidEncoding(["cp874", "dos-874"], "cp874"),
    "cp1255": ValidEncoding(["cp1255", "windows-1255"], "cp1255"),
    "cp1256": ValidEncoding(["cp1256", "windows-1256"], "cp1256"),
    "cp1250": ValidEncoding(["cp1250", "windows-1250"], "cp1250"),
    "cp1251": ValidEncoding(["cp1251", "windows-1251"], "cp1251"),
    "cp1254": ValidEncoding(["cp1254", "windows-1254"], "cp1254"),
    "cp1253": ValidEncoding(["cp1253", "windows-1253"], "cp1253"),
    "gbk": ValidEncoding(["gbk", "gb2312"], "gbk"),
    "big5": ValidEncoding(["big5"], "big5"),
    "shift_jis": ValidEncoding(["shift_jis", "sjis"], "shift_jis"),
    "euc-jp": ValidEncoding(["euc-jp", "euc-jp"], "euc-jp"),
    "euc-kr": ValidEncoding(["euc-kr"], "euc-kr"),
}


def _list_valid_encodings():
    """List all valid encodings."""
    valid_encodings = []

    for encoding in _supported_encodings.values():
        valid_encodings.extend(encoding.values())

    return valid_encodings


def validate_encoding(encoding: str) -> bool:
    """Validate and normalize encoding names"""
    if encoding is None:
        return False

    encoding = encoding.lower()

    if encoding in _list_valid_encodings():
        return True
