"""Shared local-file mechanics for concrete infrastructure providers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from sugarprep.domain.dataset import DatasetRef
from sugarprep.domain.errors import SugarPrepError


class LocalFileResolutionError(SugarPrepError):
    pass


def resolve_local_file(reference: DatasetRef) -> Path:
    locator = reference.storage_locator
    if locator.lower().startswith("file:"):
        parsed = urlparse(locator)
        if parsed.scheme.lower() != "file" or parsed.netloc not in ("", "localhost"):
            raise LocalFileResolutionError("only local file locators are supported")
        path_text = url2pathname(unquote(parsed.path))
        if len(path_text) >= 3 and path_text[0] in ("/", "\\") and path_text[2] == ":":
            path_text = path_text[1:]
        path = Path(path_text)
    else:
        path = Path(locator)
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise LocalFileResolutionError("dataset locator does not resolve to a readable file")
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise LocalFileResolutionError(f"unable to fingerprint local file: {exc}") from exc
    return digest.hexdigest()
