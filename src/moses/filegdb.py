"""Bounded File Geodatabase bundles; never follow source or archive symlinks."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

MAX_MEMBERS = 100_000
MAX_UNCOMPRESSED_BYTES = 20 * 1024**3
MAX_COMPRESSION_RATIO = 1000


def reject_symlink_path(path: Path) -> None:
    """Check before resolve(), which otherwise hides a symlink input."""
    if path.is_symlink():
        raise ValueError(f"FileGDB sources cannot contain symlinks: {path}")


def directory_files(path: Path) -> list[Path]:
    reject_symlink_path(path)
    if not path.is_dir() or path.suffix.lower() != '.gdb':
        raise ValueError('FileGDB source must be a .gdb directory')
    result = []
    total = 0
    names = set()
    for root, directories, filenames in os.walk(path, followlinks=False):
        for name in directories + filenames:
            candidate = Path(root) / name
            if candidate.is_symlink():
                raise ValueError('FileGDB sources cannot contain symlinks')
            relative = candidate.relative_to(path).as_posix()
            folded = relative.casefold()
            if folded in names:
                raise ValueError('FileGDB contains colliding member names')
            names.add(folded)
            if len(names) > MAX_MEMBERS:
                raise ValueError('FileGDB exceeds the member count limit')
            if candidate.is_file():
                total += candidate.stat().st_size
                result.append(candidate)
            elif not candidate.is_dir():
                raise ValueError('FileGDB members must be regular files or directories')
            if total > MAX_UNCOMPRESSED_BYTES:
                raise ValueError('FileGDB exceeds the uncompressed byte limit')
    if not result:
        raise ValueError('FileGDB directory contains no files')
    return sorted(result, key=lambda item: item.relative_to(path).as_posix())


def bundle_digest(path: Path) -> str:
    """SHA256 of sorted relative POSIX paths and member SHA256s (no root name)."""
    digest = hashlib.sha256()
    for member in directory_files(path):
        name = member.relative_to(path).as_posix().encode('utf-8')
        digest.update(len(name).to_bytes(8, 'big'))
        digest.update(name)
        contents = hashlib.sha256()
        with member.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                contents.update(block)
        digest.update(contents.digest())
    return digest.hexdigest()


def copy_directory(source: Path, target: Path) -> None:
    before = bundle_digest(source)
    files = directory_files(source)
    target.mkdir()
    for root, directories, _ in os.walk(source, followlinks=False):
        for name in directories:
            directory = Path(root) / name
            if directory.is_symlink():
                raise ValueError('FileGDB sources cannot contain symlinks')
            (target / directory.relative_to(source)).mkdir(parents=True, exist_ok=True)
    for original in files:
        destination = target / original.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, destination, follow_symlinks=False)
        if not destination.is_file() or destination.is_symlink():
            raise ValueError('FileGDB source changed while being captured')
    if bundle_digest(source) != before or bundle_digest(target) != before:
        raise RuntimeError('FileGDB source changed while being captured; retry import')


def _archive_members(archive: zipfile.ZipFile):
    members = archive.infolist()
    if not members or len(members) > MAX_MEMBERS:
        raise ValueError('FileGDB archive has no members or exceeds the member count limit')
    seen = set()
    roots = set()
    total = 0
    files = []
    for item in members:
        name = item.filename
        parts = name.rstrip('/').split('/')
        member = PurePosixPath(name)
        if (not name or '\\' in name or '\x00' in name or member.is_absolute()
                or any(part in ('', '.', '..') or ':' in part for part in parts)):
            raise ValueError('FileGDB archive contains an unsafe member path')
        normalized = member.as_posix().rstrip('/').casefold()
        if normalized in seen:
            raise ValueError('FileGDB archive contains duplicate member names')
        seen.add(normalized)
        mode = item.external_attr >> 16
        if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
            raise ValueError('FileGDB archive members cannot be symlinks or special files')
        if item.flag_bits & 1:
            raise ValueError('Encrypted FileGDB archives are unsupported')
        roots.add(parts[0])
        if not parts[0].lower().endswith('.gdb') or (len(parts) == 1 and not item.is_dir()):
            raise ValueError('FileGDB archive must contain exactly one root .gdb directory')
        if not item.is_dir():
            total += item.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise ValueError('FileGDB archive exceeds the uncompressed byte limit')
            if item.file_size > max(item.compress_size, 1) * MAX_COMPRESSION_RATIO:
                raise ValueError('FileGDB archive exceeds the compression ratio limit')
            files.append(item)
    if len(roots) != 1 or not files:
        raise ValueError('FileGDB archive must contain exactly one root .gdb directory')
    # Reject a regular file used as a parent before extraction begins.
    file_names = {item.filename.casefold() for item in files}
    for item in members:
        if any(parent.as_posix().casefold() in file_names for parent in PurePosixPath(item.filename).parents if parent.as_posix() != '.'):
            raise ValueError('FileGDB archive contains conflicting member paths')
    return next(iter(roots)), files


@contextmanager
def reader_directory(path: Path):
    if path.is_dir():
        directory_files(path)
        yield path
        return
    reject_symlink_path(path)
    try:
        with zipfile.ZipFile(path) as archive:
            root, files = _archive_members(archive)
            with tempfile.TemporaryDirectory(prefix='moses-filegdb-') as temporary:
                destination = Path(temporary)
                for item in files:
                    target = destination / item.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(item) as source, target.open('xb') as output:
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                yield destination / root
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError('FileGDB source is not a valid readable archive') from exc
