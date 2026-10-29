
"""Verify reusable builds using content hashes.

Only safe when the caller supplies the complete set of build inputs.
No compilation, installation, or game-file modification.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile

SCHEMA = 1


def snapshot(files):
    if not files:
        raise ValueError("Build inputs/outputs cannot be empty")

    result = {}
    for name, filename in sorted(files.items()):
        path = Path(filename)
        if not path.is_file():
            raise FileNotFoundError(str(path))

        h = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                h.update(chunk)

        result[name] = {
            "sha256": h.hexdigest(),
            "size": path.stat().st_size,
        }

    return result


def reusable(receipt, inputs, outputs):
    path = Path(receipt)
    if not path.is_file():
        return False

    try:
        saved = json.loads(path.read_text(encoding="utf-8"))

        return (
            saved.get("schema") == SCHEMA
            and saved.get("inputs") == snapshot(inputs)
            and saved.get("outputs") == snapshot(outputs)
        )
    except (OSError, ValueError, TypeError, KeyError):
        return False


def record(receipt, inputs, outputs):
    document = {
        "schema": SCHEMA,
        "inputs": snapshot(inputs),
        "outputs": snapshot(outputs),
    }

    path = Path(receipt)
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".receipt-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())

        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
