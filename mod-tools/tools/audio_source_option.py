"""Resolve genuine locally owned FFBE CRI SE.acb rather than a stale S: path.

The particles do not require this bank. Audio does. This module never downloads,
fabricates, or substitutes sounds; it only imports a valid local bank when found.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil


class BadAudioBank(ValueError):
    pass


def valid_bank(path):
    """Basic header sanity check; decoding and cue validation happen downstream."""
    try:
        path = Path(path)
        if not path.is_file() or path.stat().st_size < 1024:
            return False
        with path.open('rb') as f:
            return f.read(4) == b'@UTF'
    except (OSError, ValueError):
        return False


def bank_candidates(root):
    root = Path(root)
    local = Path(os.environ.get('LOCALAPPDATA') or (Path.home()/'AppData/Local'))
    env = os.environ.get('FFBE_SE_ACB')
    if env:
        yield Path(env)
    yield root/'data/ffbe/audio/SE.acb'
    yield local/'FFR Vision Studio/engine/data/ffbe/audio/SE.acb'
    yield root/'build/ffbe_cpk/audio/SE.acb'
    yield root/'build/ffbe_cpk/SE.acb'
    yield root/'build/diagnostics/ffbe-memorial/SE.acb'
    yield root/'build/diagnostics/ffbe-memorial/audio/SE.acb'
    yield Path.home()/'Downloads/SE.acb'
    yield Path('S:/FFBE JP Data Export/public/SE.acb')


def ensure_local_bank(root):
    """Make a verified original SE.acb available to the project's renderer.

    Searches only known locations. The environment variable FFBE_SE_ACB
    explicitly selects a custom path. Never overwrite an existing sound bank.
    """
    root=Path(root)
    dest=root/'data/ffbe/audio/SE.acb'
    custom=os.environ.get('FFBE_SE_ACB')
    if custom:
        path=Path(custom)
        if not valid_bank(path):
            raise BadAudioBank('FFBE_SE_ACB must point to a real CRI SE.acb file: '+str(path))
    for path in bank_candidates(root):
        if not valid_bank(path):
            continue
        if path.resolve() == dest.resolve():
            return dest
        if dest.exists():
            raise BadAudioBank('Existing repository SE.acb must be reviewed; refusing to overwrite: '+str(dest))
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,dest)
        if not valid_bank(dest):
            dest.unlink(missing_ok=True)
            raise BadAudioBank('Copied FFBE SE.acb failed basic validation')
        print('IMPORTED locally owned original FFBE sound bank:', path,flush=True)
        return dest
    return None
