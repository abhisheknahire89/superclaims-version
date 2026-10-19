"""ZIP validation without extracting paths to disk; reject the entire bundle before ingest."""
import io
import stat
import zipfile
from pathlib import PurePosixPath
from .extraction.pages import sniff_mime

MAX_TOTAL = 100 * 1024 * 1024


def unpack(data: bytes) -> list[tuple[str, bytes]]:
    if len(data) > 50 * 1024 * 1024:
        raise ValueError('ZIP_SIZE_LIMIT')
    files, total = [], 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        if len(members) > 50:
            raise ValueError('ZIP_MEMBER_LIMIT')
        names = set()
        for info in members:
            name = info.filename
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or '\x00' in name or name in names:
                raise ValueError('ZIP_UNSAFE_PATH')
            names.add(name)
            if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                raise ValueError('ZIP_UNSAFE_MEMBER')
            if info.is_dir():
                continue
            total += info.file_size
            if total > MAX_TOTAL or info.file_size > 50*1024*1024 or info.file_size > max(1, info.compress_size)*100:
                raise ValueError('ZIP_EXPANSION_LIMIT')
            payload = archive.read(info)
            if sniff_mime(payload) not in {'application/pdf','image/png','image/jpeg','image/tiff'}:
                raise ValueError('ZIP_UNSUPPORTED_MEMBER')
            files.append((path.name, payload))
    if not files:
        raise ValueError('ZIP_EMPTY')
    return files
