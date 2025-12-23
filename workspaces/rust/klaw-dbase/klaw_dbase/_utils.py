from __future__ import annotations


class ValidEncoding:
    """Class to represent valid encodings."""

    def __init__(self, value: str | list[str], target_encoding: str) -> None:
        self.value = value
        self.target_encoding = target_encoding

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f'ValidEncoding({self.value!r}, {self.target_encoding!r})'

    def values(self) -> list[str]:
        if isinstance(self.value, str):
            return [self.value]
        return self.value


# Supported encodings using encoding_rs for Send + Sync compatibility
_supported_encodings = {
    # UTF-8 encodings
    'utf8': ValidEncoding(['utf8', 'utf-8'], 'utf8'),
    'utf8-lossy': ValidEncoding(['utf8-lossy', 'utf-8-lossy'], 'utf8-lossy'),
    'ascii': ValidEncoding(['ascii'], 'ascii'),
    # Windows code pages (all supported by encoding_rs)
    'cp1252': ValidEncoding(['cp1252', 'windows-1252'], 'cp1252'),
    'cp1250': ValidEncoding(['cp1250', 'windows-1250'], 'cp1250'),
    'cp1251': ValidEncoding(['cp1251', 'windows-1251'], 'cp1251'),
    'cp1253': ValidEncoding(['cp1253', 'windows-1253'], 'cp1253'),
    'cp1254': ValidEncoding(['cp1254', 'windows-1254'], 'cp1254'),
    'cp1255': ValidEncoding(['cp1255', 'windows-1255'], 'cp1255'),
    'cp1256': ValidEncoding(['cp1256', 'windows-1256'], 'cp1256'),
    'cp1257': ValidEncoding(['cp1257', 'windows-1257'], 'cp1257'),
    'cp1258': ValidEncoding(['cp1258', 'windows-1258'], 'cp1258'),
    # IBM/DOS code pages supported by encoding_rs
    'cp866': ValidEncoding(['cp866', 'ibm866', 'dos-866'], 'cp866'),
    'cp874': ValidEncoding(['cp874', 'windows-874', 'dos-874'], 'cp874'),
    # ISO-8859 encodings (supported by encoding_rs)
    'iso-8859-1': ValidEncoding(['iso-8859-1', 'iso8859-1', 'latin1'], 'iso-8859-1'),
    'iso-8859-2': ValidEncoding(['iso-8859-2', 'iso8859-2', 'latin2'], 'iso-8859-2'),
    'iso-8859-7': ValidEncoding(['iso-8859-7', 'iso8859-7', 'greek'], 'iso-8859-7'),
    'iso-8859-15': ValidEncoding(['iso-8859-15', 'iso8859-15', 'latin9'], 'iso-8859-15'),
    # CJK encodings (all supported by encoding_rs)
    'gbk': ValidEncoding(['gbk', 'gb2312', 'gb18030'], 'gbk'),
    'big5': ValidEncoding(['big5'], 'big5'),
    'shift_jis': ValidEncoding(['shift_jis', 'sjis', 'shift-jis'], 'shift_jis'),
    'euc-jp': ValidEncoding(['euc-jp', 'eucjp'], 'euc-jp'),
    'euc-kr': ValidEncoding(['euc-kr', 'euckr'], 'euc-kr'),
}


def _list_valid_encodings():
    """List all valid encodings."""
    valid_encodings = []

    for encoding in _supported_encodings.values():
        valid_encodings.extend(encoding.values())

    return valid_encodings


def validate_encoding(encoding: str) -> bool:
    """Validate and normalize encoding names."""
    if encoding is None:
        return False

    encoding = encoding.lower()

    if encoding in _list_valid_encodings():
        return True
    return None
