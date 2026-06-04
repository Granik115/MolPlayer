"""
Playlists storage and management.
Stores playlists as list of absolute file paths.
Persists to %LOCALAPPDATA%\MolPlayer\playlists.json
When adding folder: recursively? No, top-level files only (can change later).
Filters only known audio extensions. Tries to read basic metadata with mutagen.
Skips unreadable or non-audio silently.
"""

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from mutagen import File as MutagenFile

from constants import AUDIO_EXTS, APP_NAME


def get_app_data_dir() -> Path:
    local = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    d = Path(local) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


PLAYLISTS_FILE = get_app_data_dir() / "playlists.json"


@dataclass
class Track:
    path: str
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0.0  # seconds

    def display_name(self) -> str:
        if self.title:
            if self.artist:
                return f"{self.artist} — {self.title}"
            return self.title
        return os.path.basename(self.path)


@dataclass
class Playlist:
    name: str
    tracks: List[Track] = field(default_factory=list)
    # We don't store order separately; the list is the order.

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tracks": [asdict(t) for t in self.tracks],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Playlist":
        tracks = [Track(**t) for t in d.get("tracks", [])]
        return cls(name=d.get("name", "Untitled"), tracks=tracks)


class PlaylistManager:
    def __init__(self):
        self.playlists: List[Playlist] = []
        self._current: Optional[Playlist] = None
        self.load()

    def load(self):
        if not PLAYLISTS_FILE.exists():
            self.playlists = []
            return
        try:
            data = json.loads(PLAYLISTS_FILE.read_text(encoding="utf-8"))
            self.playlists = [Playlist.from_dict(p) for p in data.get("playlists", [])]
        except Exception as e:
            print(f"[PlaylistManager] load error: {e}")
            self.playlists = []

    def save(self):
        try:
            data = {"playlists": [p.to_dict() for p in self.playlists]}
            PLAYLISTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[PlaylistManager] save error: {e}")

    def create_playlist(self, name: str) -> Playlist:
        # unique name
        base = name.strip() or "New Playlist"
        name = base
        i = 2
        while any(p.name.lower() == name.lower() for p in self.playlists):
            name = f"{base} ({i})"
            i += 1
        pl = Playlist(name=name)
        self.playlists.append(pl)
        self.save()
        return pl

    def delete_playlist(self, name: str) -> bool:
        before = len(self.playlists)
        self.playlists = [p for p in self.playlists if p.name != name]
        if self._current and self._current.name == name:
            self._current = None
        changed = len(self.playlists) < before
        if changed:
            self.save()
        return changed

    def rename_playlist(self, old: str, new: str) -> bool:
        new = new.strip()
        if not new or any(p.name.lower() == new.lower() for p in self.playlists if p.name != old):
            return False
        for p in self.playlists:
            if p.name == old:
                p.name = new
                if self._current and self._current.name == old:
                    self._current.name = new
                self.save()
                return True
        return False

    def get_playlist(self, name: str) -> Optional[Playlist]:
        for p in self.playlists:
            if p.name == name:
                return p
        return None

    def set_current(self, name: str) -> Optional[Playlist]:
        pl = self.get_playlist(name)
        self._current = pl
        return pl

    def get_current(self) -> Optional[Playlist]:
        return self._current

    def add_folder(self, folder: str, playlist: Optional[Playlist] = None) -> Tuple[int, int, List[str]]:
        """
        Scan folder (non-recursive top level) for audio files.
        Returns (added_count, skipped_count, skipped_examples)
        Silently ignores files with bad extension or that fail to be read by mutagen.
        """
        if playlist is None:
            playlist = self._current
        if playlist is None:
            return 0, 0, []

        p = Path(folder)
        if not p.is_dir():
            return 0, 0, []

        added = 0
        skipped = 0
        skipped_examples: List[str] = []

        existing_paths = {t.path for t in playlist.tracks}

        for entry in p.iterdir():
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext not in AUDIO_EXTS:
                continue
            path_str = str(entry.resolve())
            if path_str in existing_paths:
                continue

            track = self._make_track(path_str)
            if track is None:
                skipped += 1
                if len(skipped_examples) < 3:
                    skipped_examples.append(entry.name)
                continue

            playlist.tracks.append(track)
            existing_paths.add(path_str)
            added += 1

        if added > 0:
            self.save()
        return added, skipped, skipped_examples

    def _make_track(self, path: str) -> Optional[Track]:
        try:
            audio = MutagenFile(path, easy=True)
            if audio is None:
                # still allow if pygame can play it
                title = ""
                artist = ""
                album = ""
                duration = 0.0
            else:
                title = (audio.get("title") or [None])[0] or ""
                artist = (audio.get("artist") or [None])[0] or ""
                album = (audio.get("album") or [None])[0] or ""
                try:
                    duration = float(audio.info.length) if audio.info else 0.0
                except Exception:
                    duration = 0.0

            # Fallback title from filename
            if not title:
                title = Path(path).stem

            return Track(
                path=path,
                title=title,
                artist=artist,
                album=album,
                duration=duration,
            )
        except Exception as e:
            # Try minimal: still create with filename if file seems playable
            try:
                # quick existence + ext check already done
                return Track(
                    path=path,
                    title=Path(path).stem,
                    duration=0.0,
                )
            except Exception:
                return None

    def remove_track(self, playlist_name: str, track_path: str) -> bool:
        pl = self.get_playlist(playlist_name)
        if not pl:
            return False
        before = len(pl.tracks)
        pl.tracks = [t for t in pl.tracks if t.path != track_path]
        if len(pl.tracks) < before:
            self.save()
            return True
        return False

    def clear_playlist(self, name: str) -> bool:
        pl = self.get_playlist(name)
        if not pl:
            return False
        if pl.tracks:
            pl.tracks = []
            self.save()
            return True
        return False

    def move_track(self, name: str, from_idx: int, to_idx: int) -> bool:
        """Optional for future drag reorder."""
        pl = self.get_playlist(name)
        if not pl or not (0 <= from_idx < len(pl.tracks)):
            return False
        track = pl.tracks.pop(from_idx)
        to_idx = max(0, min(to_idx, len(pl.tracks)))
        pl.tracks.insert(to_idx, track)
        self.save()
        return True
