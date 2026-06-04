"""
Audio playback engine using pygame.mixer.
Handles play/pause/stop/seek/volume + position polling.
Note: pygame seek (set_pos) works best with WAV/OGG, for MP3 it's approximate but usable.
"""

import os
import time
import threading
from typing import Optional, Callable

import pygame

from constants import AUDIO_EXTS


class AudioEngine:
    def __init__(self):
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        self._current_path: Optional[str] = None
        self._length: float = 0.0  # seconds
        self._volume: float = 0.7
        pygame.mixer.music.set_volume(self._volume)

        # Wall-clock based position tracking (more reliable than relying on pygame.get_pos after pause/resume)
        self._segment_start_pos: float = 0.0   # track position at start of current playback segment
        self._segment_start_wall: float = 0.0  # time.monotonic() when segment started
        self._paused_pos: float = 0.0
        self._is_playing: bool = False
        self._is_paused: bool = False

        self._end_callback: Optional[Callable[[], None]] = None
        self._poll_thread: Optional[threading.Thread] = None
        self._stop_poll = threading.Event()

    def set_end_callback(self, cb: Callable[[], None]):
        self._end_callback = cb

    def _get_file_length(self, path: str) -> float:
        """Try to get duration using pygame (or 0). Mutagen is better but done in manager."""
        try:
            # pygame has no direct duration API for music until recently; use 0 and rely on manager
            # We set length from outside via set_length
            return 0.0
        except Exception:
            return 0.0

    def set_length(self, length: float):
        """Called by UI/manager after loading tags."""
        self._length = max(0.0, length)

    def load(self, path: str) -> bool:
        """Load a track. Returns True on success."""
        if not os.path.isfile(path):
            return False
        ext = os.path.splitext(path)[1].lower()
        if ext not in AUDIO_EXTS:
            return False
        try:
            pygame.mixer.music.load(path)
            self._current_path = path
            self._segment_start_pos = 0.0
            self._paused_pos = 0.0
            self._is_playing = False
            self._is_paused = False
            self._segment_start_wall = 0.0
            # length will be set externally
            return True
        except Exception as e:
            print(f"[AudioEngine] load failed: {e}")
            self._current_path = None
            return False

    def play(self, start_from: float = 0.0) -> bool:
        """Start or resume playback. start_from in seconds.
        Uses wall time for position to avoid jumps after pause/resume on mp3.
        """
        if not self._current_path:
            return False
        try:
            # Always stop first for clean state
            pygame.mixer.music.stop()
            time.sleep(0.01)

            start_pos = max(0.0, start_from)
            try:
                pygame.mixer.music.play(start=start_pos)
            except Exception:
                pygame.mixer.music.play()
                try:
                    pygame.mixer.music.set_pos(start_pos)
                except Exception:
                    pass

            self._segment_start_pos = start_pos
            self._segment_start_wall = time.monotonic()
            self._is_playing = True
            self._is_paused = False
            self._paused_pos = 0.0

            self._start_end_poll()
            return True
        except Exception as e:
            print(f"[AudioEngine] play failed: {e}")
            return False

    def pause(self):
        if self._is_playing and pygame.mixer.music.get_busy():
            self._paused_pos = self.get_pos()
            pygame.mixer.music.pause()
            self._is_playing = False
            self._is_paused = True
            self._stop_end_poll()

    def resume(self):
        if self._current_path and self._is_paused:
            # Restart wall clock from the paused position (key to preventing jumps)
            self._segment_start_pos = self._paused_pos
            self._segment_start_wall = time.monotonic()
            pygame.mixer.music.unpause()
            self._is_playing = True
            self._is_paused = False
            self._start_end_poll()

    def stop(self):
        pygame.mixer.music.stop()
        self._is_playing = False
        self._is_paused = False
        self._segment_start_pos = 0.0
        self._paused_pos = 0.0
        self._segment_start_wall = 0.0
        self._stop_end_poll()

    def is_playing(self) -> bool:
        return self._is_playing and bool(pygame.mixer.music.get_busy())

    def is_paused(self) -> bool:
        return self._is_paused and bool(self._current_path)

    def get_pos(self) -> float:
        """Current playback position in seconds.
        Primary source is wall-clock time since last play/seek/resume.
        This avoids large jumps common with pygame.get_pos() after pause on MP3.
        """
        if not self._current_path:
            return 0.0
        if self._is_paused:
            return self._paused_pos
        if not self._is_playing:
            return self._segment_start_pos

        # Wall time elapsed since segment start
        elapsed = time.monotonic() - self._segment_start_wall
        pos = self._segment_start_pos + max(0.0, elapsed)

        if self._length > 0 and pos > self._length + 0.2:
            pos = self._length
        return pos

    def seek(self, pos: float):
        """Seek to position (seconds). Will restart playback from there.
        Uses clean stop + play(start=) + wall time reset.
        """
        if not self._current_path:
            return
        pos = max(0.0, min(pos, self._length or 999999.0))
        was_paused = self._is_paused

        try:
            pygame.mixer.music.stop()
            time.sleep(0.015)
        except Exception:
            pass

        try:
            pygame.mixer.music.play(start=pos)
        except Exception:
            pygame.mixer.music.play()
            try:
                pygame.mixer.music.set_pos(pos)
            except Exception:
                pass

        self._segment_start_pos = pos
        self._segment_start_wall = time.monotonic()
        self._paused_pos = pos
        self._is_playing = True
        self._is_paused = False

        if was_paused:
            pygame.mixer.music.pause()
            self._is_playing = False
            self._is_paused = True
            self._stop_end_poll()
        else:
            self._start_end_poll()

    def set_volume(self, vol: float):
        vol = max(0.0, min(1.0, vol))
        self._volume = vol
        pygame.mixer.music.set_volume(vol)

    def get_volume(self) -> float:
        return self._volume

    def get_current_path(self) -> Optional[str]:
        return self._current_path

    def get_length(self) -> float:
        return self._length

    def _start_end_poll(self):
        self._stop_end_poll()
        self._stop_poll.clear()
        self._poll_thread = threading.Thread(target=self._poll_end, daemon=True)
        self._poll_thread.start()

    def _stop_end_poll(self):
        self._stop_poll.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=0.2)
        self._poll_thread = None

    def _poll_end(self):
        """Watch for natural end of track and fire callback."""
        while not self._stop_poll.is_set():
            if not self._current_path:
                break
            busy = pygame.mixer.music.get_busy()
            if not busy and not self._is_paused:
                # natural end or error
                if self._end_callback:
                    try:
                        self._end_callback()
                    except Exception:
                        pass
                break
            time.sleep(0.25)

    def cleanup(self):
        self._stop_end_poll()
        try:
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except Exception:
            pass
