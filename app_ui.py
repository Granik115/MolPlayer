"""
MolPlayer - main application.
Minecraft Molecular Transformer inspired dark tech UI (blue/cyan theme).
Vertical split (playlists | content), horizontal actions | tracks, FULL-WIDTH now-playing bar docked at bottom of tracks area.
"""

import os
import random
import sys
import threading
import time
from pathlib import Path
from typing import Optional, List

import customtkinter as ctk
from tkinter import filedialog, messagebox
import pygame  # only for init check if needed

import urllib.request
import json as _json
import zipfile
import tempfile
import shutil
import subprocess
import sys
import os
import threading

# Local
from constants import (
    BG_DARK, BG_SIDEBAR, BG_PANEL, BG_TRACK, BG_TRACK_HOVER, BG_TRACK_SELECTED,
    BG_OVERLAY,
    ACCENT_BLUE, ACCENT_BLUE_HOVER, ACCENT_CYAN, ACCENT_CYAN_HOVER,
    ACCENT_FRAME, ACCENT_GLOW, ACCENT_GLOW_TEAL, DEPTH_BLUE, BTN_PRIMARY, BTN_PRIMARY_HOVER,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    PROGRESS_BG, PROGRESS_FILL_BLUE, PROGRESS_FILL_CYAN,
    BTN_BG, BTN_HOVER, BORDER,
    APP_NAME, APP_VERSION, AUDIO_EXTS
)
from audio_engine import AudioEngine
from playlist_manager import PlaylistManager, Playlist, Track, get_app_data_dir


# Make customtkinter look dark techy
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")  # base, we override many colors manually


def format_time(seconds: float) -> str:
    if seconds is None or seconds < 0:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


class TrackRow(ctk.CTkFrame):
    """Custom row for a single track in the playlist view."""
    def __init__(self, master, track: Track, index: int, on_play, on_remove, on_select, **kwargs):
        super().__init__(master, fg_color=BG_TRACK, corner_radius=4, **kwargs)
        self.track = track
        self.index = index
        self.on_play = on_play
        self.on_remove = on_remove
        self.on_select = on_select
        self._selected = False
        self._playing = False
        self._hovered = False

        self.grid_columnconfigure(1, weight=1)

        # Number
        self.lbl_num = ctk.CTkLabel(
            self, text=f"{index+1:02d}", width=32,
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=11)
        )
        self.lbl_num.grid(row=0, column=0, padx=(8, 4), pady=4, sticky="w")

        # Main title / artist
        name = track.display_name()
        self.lbl_name = ctk.CTkLabel(
            self, text=name, anchor="w",
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=13, weight="normal")
        )
        self.lbl_name.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        # Duration
        dur = format_time(track.duration)
        self.lbl_dur = ctk.CTkLabel(
            self, text=dur, width=56, anchor="e",
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=11)
        )
        self.lbl_dur.grid(row=0, column=2, padx=(4, 4), pady=4, sticky="e")

        # Remove button (small X)
        self.btn_del = ctk.CTkButton(
            self, text="✕", width=26, height=22,
            fg_color="transparent", hover_color="#3A2A2A",
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=12),
            command=self._do_remove
        )
        self.btn_del.grid(row=0, column=3, padx=(2, 8), pady=3, sticky="e")

        # Bind clicks - single click now plays the track (as requested)
        for w in (self, self.lbl_num, self.lbl_name, self.lbl_dur):
            w.bind("<Button-1>", self._on_double)  # single click to play
            # Double click also plays (for users used to it)
            w.bind("<Double-Button-1>", self._on_double)

        # Bind hover to all parts of the row so hover works over labels and delete button too
        for w in (self, self.lbl_num, self.lbl_name, self.lbl_dur, self.btn_del):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)

    def _on_enter(self, _=None):
        self._hovered = True
        self._apply_color()

    def _on_leave(self, _=None):
        self._hovered = False
        self._apply_color()

    def set_selected(self, sel: bool):
        self._selected = sel
        self._apply_color()

    def set_playing(self, playing: bool):
        self._playing = playing
        self._apply_color()

    def _apply_color(self):
        if getattr(self, "_playing", False):
            self.configure(fg_color=DEPTH_BLUE)
            self.lbl_num.configure(text_color=ACCENT_GLOW)
        elif self._selected:
            self.configure(fg_color=BG_TRACK_SELECTED)
            self.lbl_num.configure(text_color=TEXT_MUTED)
        elif self._hovered:
            self.configure(fg_color=BG_TRACK_HOVER)
            self.lbl_num.configure(text_color=TEXT_MUTED)
        else:
            self.configure(fg_color=BG_TRACK)
            self.lbl_num.configure(text_color=TEXT_MUTED)

    def _on_click(self, _=None):
        if self.on_select:
            self.on_select(self)

    def _on_double(self, _=None):
        if self.on_play:
            self.on_play(self.track, self.index)

    def _do_remove(self):
        if self.on_remove:
            self.on_remove(self.track, self.index)


class NowPlayingPanel(ctk.CTkFrame):
    """Full-width now-playing control bar at the bottom of the tracks area.
    Uses blue/cyan theme. No orange. Stop button removed per request.
    """
    def __init__(self, master, audio: AudioEngine, on_prev, on_next, on_toggle, on_seek, **kwargs):
        super().__init__(master, fg_color=BG_OVERLAY, corner_radius=4, border_width=1, border_color=BORDER, **kwargs)
        self.audio = audio
        self.on_prev = on_prev
        self.on_next = on_next
        self.on_toggle = on_toggle
        self.on_seek = on_seek

        self.current_track: Optional[Track] = None

        # Layout - 3 columns for nice centering of transport controls
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)   # centered transport controls
        self.grid_columnconfigure(2, weight=1)

        # Top row: title
        self.lbl_title = ctk.CTkLabel(
            self, text="Нет воспроизведения", anchor="w",
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_title.grid(row=0, column=0, columnspan=3, padx=10, pady=(6, 2), sticky="ew")

        # Progress row - full width
        self.progress_var = ctk.DoubleVar(value=0.0)
        self.progress = ctk.CTkSlider(
            self, from_=0, to=1, variable=self.progress_var,
            button_color=ACCENT_GLOW, button_hover_color=ACCENT_GLOW_TEAL,
            progress_color=ACCENT_GLOW, fg_color=PROGRESS_BG,
            height=8, command=self._on_seek_slider
        )
        self.progress.grid(row=1, column=0, columnspan=3, padx=10, pady=(2, 4), sticky="ew")

        # Bottom control row
        # Left: time
        self.lbl_time = ctk.CTkLabel(self, text="0:00 / 0:00", text_color=TEXT_MUTED, font=ctk.CTkFont(size=10))
        self.lbl_time.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="w")

        # Center: transport controls (prev / play-pause / next) - this is the main request
        transport_frame = ctk.CTkFrame(self, fg_color="transparent")
        transport_frame.grid(row=2, column=1, padx=4, pady=(0, 6), sticky="")

        self.btn_prev = ctk.CTkButton(transport_frame, text="⏮", width=32, height=28,
                                      fg_color=BTN_BG, hover_color=BTN_HOVER,
                                      command=self.on_prev)
        self.btn_prev.pack(side="left", padx=2)

        self.btn_toggle = ctk.CTkButton(transport_frame, text="▶", width=36, height=28,
                                        fg_color=BTN_BG, hover_color=BTN_HOVER,
                                        command=self.on_toggle)
        self.btn_toggle.pack(side="left", padx=2)

        self.btn_next = ctk.CTkButton(transport_frame, text="⏭", width=32, height=28,
                                      fg_color=BTN_BG, hover_color=BTN_HOVER,
                                      command=self.on_next)
        self.btn_next.pack(side="left", padx=2)

        # Right: volume
        self.vol_var = ctk.DoubleVar(value=self.audio.get_volume())
        self.vol_slider = ctk.CTkSlider(
            self, from_=0, to=1, variable=self.vol_var,
            width=150, height=14, button_length=12,
            button_color=ACCENT_GLOW, progress_color=ACCENT_GLOW,
            command=self._on_vol_change
        )
        self.vol_slider.grid(row=2, column=2, padx=(4, 10), pady=(0, 6), sticky="e")

        self._dragging_seek = False

    def _on_vol_change(self, v):
        self.audio.set_volume(v)

    def _on_seek_slider(self, val):
        # Only seek when user releases? For simplicity we live-seek (a bit heavy but ok)
        if self.current_track and self.current_track.duration > 0:
            target = val * self.current_track.duration
            if self.on_seek:
                self.on_seek(target)

    def update_state(self, track: Optional[Track], pos: float, is_playing: bool, is_paused: bool):
        self.current_track = track

        if track is None:
            self.lbl_title.configure(text="Нет воспроизведения")
            self.progress_var.set(0)
            self.lbl_time.configure(text="0:00 / 0:00")
            self.btn_toggle.configure(text="▶")
            return

        title = track.display_name()
        if len(title) > 42:
            title = title[:39] + "…"
        self.lbl_title.configure(text=title)

        length = track.duration or self.audio.get_length() or 1.0
        frac = max(0.0, min(1.0, pos / length)) if length > 0 else 0
        if not self._dragging_seek:
            self.progress_var.set(frac)

        self.lbl_time.configure(text=f"{format_time(pos)} / {format_time(length)}")

        if is_playing:
            self.btn_toggle.configure(text="⏸")
        else:
            self.btn_toggle.configure(text="▶")

    def set_dragging(self, d: bool):
        self._dragging_seek = d


class MolPlayerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — {APP_VERSION}")

        # State - create manager early to restore window position, sidebar, opacity, autostart before showing
        self.manager = PlaylistManager()
        state = self.manager.load_app_state()
        window_geometry = state.get("window_geometry")
        if window_geometry:
            try:
                self.geometry(window_geometry)
            except Exception:
                self.geometry("1100x680")
        else:
            self.geometry("1100x680")

        self.minsize(900, 560)

        # Load persisted UI prefs (defaults per spec)
        self._sidebar_width = max(160, min(520, int(state.get("sidebar_width", 260))))
        self._opacity = max(0.1, min(1.0, float(state.get("opacity", 1.0))))
        self._autostart = bool(state.get("autostart", False))
        self._settings_open = False
        self.settings_frame = None
        self.btn_gear = None
        self._sash_drag_start_x = 0
        self._sash_drag_start_w = 0
        self._sash_dragging = False

        # Apply saved opacity (default 100% fully opaque). Live controlled in settings.
        try:
            self.attributes("-alpha", self._opacity)
        except Exception:
            pass  # some platforms may not support

        # State objects
        self.audio = AudioEngine()
        self.audio.set_end_callback(self._on_track_ended)

        self.current_playlist_name: Optional[str] = None
        self.current_track_idx: Optional[int] = None
        self.current_track: Optional[Track] = None
        self._play_mode: Optional[str] = None   # "sequential" or "random" - to restart the same way when playlist ends
        self.play_order: List[int] = []  # indices into current playlist

        self._track_rows: List[TrackRow] = []
        self._selected_row: Optional[TrackRow] = None
        self._ui_update_after = None
        self._closing = False

        self._build_ui()
        self._refresh_playlists_list()
        self._start_ui_poller()

        # Force initial sash placement (multiple calls + idletasks to ensure it appears)
        self.update_idletasks()
        self.after(20, self._place_sash)
        self.after(100, self._place_sash)
        self.after(300, self._place_sash)

        # Restore previous session (playlist, track, volume, mode)
        # Note: geometry already applied above
        self._restore_last_session()

        # Тихая автопроверка обновлений при запуске (через 10 секунд, чтобы не мешать)
        self.after(10000, lambda: self._check_for_updates(silent=True))

        # Global media keys support (like Spotify, YouTube, VK): play/pause, next, prev
        # Works even when app is not focused, using system media keys (fn+f5 etc. on some keyboards map to these)
        self._start_media_key_listener()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # For live updating settings panel size on window resize (height + width safety)
        self.bind("<Configure>", self._on_window_configure)

    # ---------------- UI BUILD ----------------
    def _build_ui(self):
        self.configure(fg_color=BG_DARK)

        # Main grid: left sidebar | right content (sash will be .place()'d on top for smooth drag)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # LEFT: Playlists sidebar (width from persisted or default)
        self.sidebar = ctk.CTkFrame(self, fg_color=BG_SIDEBAR, width=self._sidebar_width, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # SASH (draggable divider) - placed absolutely for reliable non-jerky behaviour
        self.sash = ctk.CTkFrame(self, fg_color=BORDER, width=5, cursor="sb_h_double_arrow")
        self.sash.bind("<Button-1>", self._on_sash_press)
        self.sash.bind("<B1-Motion>", self._on_sash_drag)
        self.sash.bind("<ButtonRelease-1>", self._on_sash_release)
        self.sash.bind("<Enter>", lambda e: self.sash.configure(fg_color=ACCENT_GLOW))
        self.sash.bind("<Leave>", lambda e: self.sash.configure(fg_color=BORDER))

        # Sidebar header
        hdr = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(12, 6))

        ctk.CTkLabel(hdr, text="ПЛЕЙЛИСТЫ", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")

        self.btn_new_pl = ctk.CTkButton(
            hdr, text="+", width=32, height=28,
            fg_color=BTN_BG, hover_color=BTN_HOVER,
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=16, weight="bold"),
            command=self._create_new_playlist
        )
        self.btn_new_pl.pack(side="right")

        # Scrollable playlists
        self.pl_scroll = ctk.CTkScrollableFrame(
            self.sidebar, fg_color=BG_SIDEBAR, label_text="",
            scrollbar_button_color=ACCENT_FRAME,
            scrollbar_button_hover_color=ACCENT_GLOW
        )
        self.pl_scroll.pack(fill="both", expand=True, padx=6, pady=4)

        self.pl_buttons: List[ctk.CTkButton] = []

        # Bottom sidebar actions
        bot = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bot.pack(fill="x", padx=8, pady=8)
        self.btn_del_pl = ctk.CTkButton(
            bot, text="Удалить плейлист", fg_color=BTN_BG, hover_color=BTN_HOVER,
            text_color=TEXT_PRIMARY, command=self._delete_current_playlist
        )
        self.btn_del_pl.pack(fill="x")

        # Version + updates
        ver_frame = ctk.CTkFrame(bot, fg_color="transparent")
        ver_frame.pack(fill="x", pady=(6, 0))
        ctk.CTkLabel(ver_frame, text=f"v{APP_VERSION}", text_color=TEXT_MUTED,
                     font=ctk.CTkFont(size=10)).pack(side="left")
        self.btn_check_updates = ctk.CTkButton(
            ver_frame, text="Обновления", width=90, height=24,
            fg_color=BTN_BG, hover_color=BTN_HOVER,
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=10),
            command=self._check_for_updates
        )
        self.btn_check_updates.pack(side="right")

        # Rollback button next to updates (small icon for previous version)
        self.btn_rollback = ctk.CTkButton(
            ver_frame, text="↩", width=26, height=24,
            fg_color=BTN_BG, hover_color=BTN_HOVER,
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=11),
            command=self._show_rollback_versions
        )
        self.btn_rollback.pack(side="right", padx=(4, 0))

        # RIGHT: Main content
        self.content = ctk.CTkFrame(self, fg_color=BG_OVERLAY, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(1, weight=1)  # tracks area grows

        # Playlist header + actions (top bar)
        self.top_bar = ctk.CTkFrame(self.content, fg_color=BG_DARK, height=58)
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        self.top_bar.grid_columnconfigure(0, weight=1)

        self.lbl_pl_name = ctk.CTkLabel(
            self.top_bar, text="Выберите плейлист", anchor="w",
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=18, weight="bold")
        )
        self.lbl_pl_name.grid(row=0, column=0, padx=16, pady=8, sticky="w")

        # Action buttons row
        actions = ctk.CTkFrame(self.top_bar, fg_color="transparent")
        actions.grid(row=0, column=1, padx=12, pady=6, sticky="e")
        self.top_actions_frame = actions  # used for settings panel width alignment (match buttons group)

        # Top action buttons - Gear (settings) | Play, Random, and Sources
        button_style = {
            "fg_color": BTN_BG,
            "hover_color": BTN_HOVER,
            "text_color": TEXT_PRIMARY,
        }

        # Small gear button for settings (left of "Воспроизведение")
        self.btn_gear = ctk.CTkButton(
            actions, text="⚙", width=34, height=32,
            fg_color=BTN_BG, hover_color=BTN_HOVER,
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=16),
            command=self._toggle_settings
        )
        self.btn_gear.pack(side="left", padx=(0, 6))

        self.btn_play = ctk.CTkButton(
            actions, text="▶ Воспроизвести", width=140, height=32,
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._play_playlist(start_random=False),
            **button_style
        )
        self.btn_play.pack(side="left", padx=3)

        self.btn_random = ctk.CTkButton(
            actions, text="🎲 Случайно", width=140, height=32,
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._play_playlist(start_random=True),
            **button_style
        )
        self.btn_random.pack(side="left", padx=3)

        self.btn_sources = ctk.CTkButton(
            actions, text="📁 Источники плейлиста", width=170, height=32,
            command=self._show_sources_menu,
            **button_style
        )
        self.btn_sources.pack(side="left", padx=3)

        # TRACKS AREA: list on top (most space), full-width now-playing bar at bottom
        self.tracks_container = ctk.CTkFrame(self.content, fg_color=BG_PANEL)
        self.tracks_container.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.tracks_container.grid_columnconfigure(0, weight=1)
        self.tracks_container.grid_rowconfigure(0, weight=1)   # tracks list expands
        self.tracks_container.grid_rowconfigure(1, weight=0)   # now playing bar fixed

        self.tracks_scroll = ctk.CTkScrollableFrame(
            self.tracks_container, fg_color=BG_PANEL, label_text="",
            scrollbar_button_color=ACCENT_FRAME,
            scrollbar_button_hover_color=ACCENT_GLOW
        )
        self.tracks_scroll.grid(row=0, column=0, sticky="nsew")

        # Now playing bar - full width at the bottom of the right panel (tracks area)
        self.now_panel = NowPlayingPanel(
            self.tracks_container,
            audio=self.audio,
            on_prev=self._prev_track,
            on_next=self._next_track,
            on_toggle=self._toggle_play,
            on_seek=self._seek_to
        )
        self.now_panel.grid(row=1, column=0, sticky="ew", padx=4, pady=(2, 6))

        # Status bar at very bottom
        self.status = ctk.CTkLabel(
            self, text="Готов", anchor="w", height=22,
            text_color=TEXT_MUTED, font=ctk.CTkFont(size=10)
        )
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8)

    # ---------------- PLAYLISTS LIST (left) ----------------
    def _refresh_playlists_list(self, select_name: Optional[str] = None):
        for b in self.pl_buttons:
            b.destroy()
        self.pl_buttons.clear()

        current_name = select_name or (self.current_playlist_name or (self.manager.get_current() and self.manager.get_current().name))

        for pl in self.manager.playlists:
            is_cur = (pl.name == current_name)
            btn = ctk.CTkButton(
                self.pl_scroll,
                text=pl.name,
                anchor="w",
                fg_color=BG_TRACK_SELECTED if is_cur else BG_TRACK,
                hover_color=BG_TRACK_HOVER,
                text_color=TEXT_PRIMARY if is_cur else TEXT_SECONDARY,
                font=ctk.CTkFont(size=13, weight="bold" if is_cur else "normal"),
                height=36,
                command=lambda n=pl.name: self._open_playlist(n)
            )
            btn.pack(fill="x", padx=4, pady=3)
            self.pl_buttons.append(btn)

    def _create_new_playlist(self):
        name = ctk.CTkInputDialog(text="Название плейлиста:", title="Новый плейлист").get_input()
        if not name:
            return
        pl = self.manager.create_playlist(name)
        self._refresh_playlists_list(select_name=pl.name)
        self._open_playlist(pl.name)

    def _delete_current_playlist(self):
        if not self.current_playlist_name:
            return
        if not messagebox.askyesno("Удалить плейлист", f"Удалить «{self.current_playlist_name}»?\nТреки останутся на диске."):
            return
        name = self.current_playlist_name
        self.manager.delete_playlist(name)
        self.current_playlist_name = None
        self.current_track_idx = None
        self.current_track = None
        self._refresh_playlists_list()
        self._refresh_tracks_list()
        self._hide_now_panel()
        if self.manager.playlists:
            self._open_playlist(self.manager.playlists[0].name)

    def _open_playlist(self, name: str):
        pl = self.manager.set_current(name)
        if not pl:
            return
        self.current_playlist_name = name
        self.current_track_idx = None
        self.current_track = None
        self._play_mode = None
        self.play_order = list(range(len(pl.tracks)))

        self._refresh_playlists_list(select_name=name)
        self.lbl_pl_name.configure(text=name)
        self._refresh_tracks_list()
        self._hide_now_panel()
        self.status.configure(text=f"Открыт плейлист: {name} ({len(pl.tracks)} треков)")

    # ---------------- TRACKS LIST ----------------
    def _refresh_tracks_list(self, highlight_path: Optional[str] = None):
        for r in self._track_rows:
            r.destroy()
        self._track_rows.clear()
        self._selected_row = None

        pl = self.manager.get_current()
        if not pl:
            return

        for i, track in enumerate(pl.tracks):
            row = TrackRow(
                self.tracks_scroll,
                track=track,
                index=i,
                on_play=self._play_track,
                on_remove=self._remove_track_from_current,
                on_select=self._select_track_row
            )
            row.pack(fill="x", padx=4, pady=2)
            self._track_rows.append(row)

            if highlight_path and track.path == highlight_path:
                row.set_selected(True)
                self._selected_row = row

        # restore playing highlight if any
        if self.current_track_idx is not None:
            for row in self._track_rows:
                if row.index == self.current_track_idx:
                    row.set_playing(True)
                    break

    def _select_track_row(self, row: TrackRow):
        if self._selected_row:
            self._selected_row.set_selected(False)
        row.set_selected(True)
        self._selected_row = row

    def _remove_track_from_current(self, track: Track, idx: int):
        if not self.current_playlist_name:
            return
        if self.manager.remove_track(self.current_playlist_name, track.path):
            # adjust current if needed
            if self.current_track and self.current_track.path == track.path:
                self._stop_playback()
                self.current_track = None
                self.current_track_idx = None
            self._refresh_tracks_list()
            self._update_play_order_after_remove(idx)

    def _update_play_order_after_remove(self, removed_idx: int):
        if not self.play_order:
            return
        new_order = []
        for i in self.play_order:
            if i == removed_idx:
                continue
            new_order.append(i if i < removed_idx else i - 1)
        self.play_order = new_order
        if self.current_track_idx is not None:
            if self.current_track_idx == removed_idx:
                self.current_track_idx = None
            elif self.current_track_idx > removed_idx:
                self.current_track_idx -= 1

    def _clear_current_playlist(self):
        if not self.current_playlist_name:
            return
        if not messagebox.askyesno("Очистить", "Удалить все треки из плейлиста? (файлы останутся)"):
            return
        if self.manager.clear_playlist(self.current_playlist_name):
            self._stop_playback()
            self.current_track = None
            self.current_track_idx = None
            self._refresh_tracks_list()
            self.play_order = []

    def _add_folder_to_current(self):
        if not self.current_playlist_name:
            messagebox.showinfo("Нет плейлиста", "Сначала создайте или выберите плейлист.")
            return
        folder = filedialog.askdirectory(title="Выберите папку с аудио")
        if not folder:
            return

        added, skipped, examples = self.manager.add_folder(folder, self.manager.get_current())
        self._refresh_tracks_list()
        # update play_order
        pl = self.manager.get_current()
        self.play_order = list(range(len(pl.tracks)))

        msg = f"Добавлено: {added}"
        if skipped > 0:
            ex = ", ".join(examples)
            msg += f" | Пропущено (не аудио/ошибка): {skipped} ({ex}{'...' if len(examples)>=3 else ''})"
        self.status.configure(text=msg)

    # ---------------- PLAYBACK ----------------
    def _play_playlist(self, start_random: bool = False):
        pl = self.manager.get_current()
        if not pl or not pl.tracks:
            messagebox.showinfo("Пусто", "В плейлисте нет треков. Добавьте папку.")
            return

        self.play_order = list(range(len(pl.tracks)))
        if start_random:
            random.shuffle(self.play_order)
            self._play_mode = "random"
            start_idx = 0
        else:
            self._play_mode = "sequential"
            start_idx = 0

        self.current_track_idx = start_idx
        track = pl.tracks[self.play_order[start_idx]]
        self._play_track(track, self.play_order[start_idx])

    def _play_track(self, track: Track, list_idx: int):
        """list_idx is the visual index in playlist.tracks"""
        pl = self.manager.get_current()
        if not pl:
            return

        # Find real order position if we have shuffled view? For simplicity we just use list_idx as source of truth for "next"
        # We keep play_order as the sequence of indices to follow.
        # If user double-clicks a specific track we start from there in current order.
        try:
            order_pos = self.play_order.index(list_idx)
        except ValueError:
            # rebuild order if desynced
            self.play_order = list(range(len(pl.tracks)))
            order_pos = list_idx

        self.current_track_idx = list_idx
        self.current_track = track

        # Load
        if not self.audio.load(track.path):
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{Path(track.path).name}")
            self._next_track(auto=True)
            return

        self.audio.set_length(track.duration or 0.0)

        if not self.audio.play(0.0):
            messagebox.showerror("Ошибка", "Не удалось начать воспроизведение.")
            return

        self._highlight_current_row()
        self._show_or_update_now_panel()
        self.status.configure(text=f"▶ {track.display_name()}")

        # Make sure we have correct order
        if not self.play_order:
            self.play_order = list(range(len(pl.tracks)))

    def _highlight_current_row(self):
        # clear previous playing
        for r in self._track_rows:
            r.set_playing(False)
        if self._selected_row:
            self._selected_row.set_selected(False)
        pl = self.manager.get_current()
        if not pl or self.current_track_idx is None:
            return
        for row in self._track_rows:
            if row.index == self.current_track_idx:
                row.set_playing(True)
                row.set_selected(True)
                self._selected_row = row
                break

    def _show_or_update_now_panel(self):
        # The bar is always visible (full width at bottom of tracks area).
        # Just refresh its content.
        self._update_now_panel()

    def _hide_now_panel(self):
        # Instead of hiding the bar, show it in "idle" state
        self.now_panel.update_state(None, 0.0, False, False)

    def _update_now_panel(self):
        pos = self.audio.get_pos() if self.audio.get_current_path() else 0.0
        playing = self.audio.is_playing()
        paused = self.audio.is_paused()
        self.now_panel.update_state(self.current_track, pos, playing, paused)

    def _toggle_play(self):
        if not self.current_track:
            # try to play first
            pl = self.manager.get_current()
            if pl and pl.tracks:
                self._play_track(pl.tracks[0], 0)
            return

        if self.audio.is_playing():
            self.audio.pause()
            self.status.configure(text="⏸ Пауза")
        elif self.audio.is_paused():
            self.audio.resume()
            self.status.configure(text=f"▶ {self.current_track.display_name()}")
        else:
            # stopped, restart current
            self.audio.play(self.audio.get_pos() or 0)

        self._update_now_panel()

    def _stop_playback(self):
        self.audio.stop()
        self._update_now_panel()
        self.status.configure(text="Остановлено")

    def _restart_playlist_same_pattern(self):
        """When the playlist naturally ends (auto), restart it using the exact same launch mode
        that was used when the user pressed "Воспроизвести" or "Случайно".
        """
        pl = self.manager.get_current()
        if not pl or not self.play_order:
            return

        # Re-apply the original pattern
        if self._play_mode == "random":
            random.shuffle(self.play_order)
        # else: keep current sequential order, just restart from beginning

        start_list_idx = self.play_order[0]
        track = pl.tracks[start_list_idx]
        self.current_track_idx = start_list_idx
        self._play_track(track, start_list_idx)
        self.status.configure(text=f"Повтор плейлиста ({self._play_mode or 'sequential'})")

    def _seek_to(self, pos: float):
        if self.current_track:
            self.audio.seek(pos)
            self._update_now_panel()

    def _prev_track(self):
        pl = self.manager.get_current()
        if not pl or not self.play_order or self.current_track_idx is None:
            return

        try:
            pos = self.play_order.index(self.current_track_idx)
        except ValueError:
            pos = 0

        new_pos = (pos - 1) % len(self.play_order)
        new_list_idx = self.play_order[new_pos]
        track = pl.tracks[new_list_idx]
        self._play_track(track, new_list_idx)

    def _next_track(self, auto: bool = False):
        pl = self.manager.get_current()
        if not pl or not self.play_order or self.current_track_idx is None:
            return

        try:
            pos = self.play_order.index(self.current_track_idx)
        except ValueError:
            pos = -1

        new_pos = pos + 1
        if new_pos >= len(self.play_order):
            # end of list
            if auto:
                # Restart the playlist using exactly the same pattern it was originally launched with
                # ("Случайно" -> reshuffle + start; normal -> sequential from beginning)
                self._restart_playlist_same_pattern()
                return
            else:
                new_pos = 0  # manual next wraps

        new_list_idx = self.play_order[new_pos]
        track = pl.tracks[new_list_idx]
        self._play_track(track, new_list_idx)

    def _on_track_ended(self):
        # Called from audio thread
        if self._closing:
            return
        # schedule on main thread
        self.after(10, lambda: self._next_track(auto=True))

    # ---------------- UI POLLER ----------------
    def _start_ui_poller(self):
        self._poll_ui()

    def _poll_ui(self):
        if self._closing:
            return
        try:
            if self.audio.get_current_path() and (self.audio.is_playing() or self.audio.is_paused()):
                self._update_now_panel()

                # Auto advance safety (if callback missed)
                pos = self.audio.get_pos()
                length = self.current_track.duration if self.current_track else self.audio.get_length()
                if length > 1 and pos >= length - 0.3 and self.audio.is_playing():
                    self.after(50, lambda: self._next_track(auto=True))
        except Exception:
            pass

        # reschedule
        self._ui_update_after = self.after(180, self._poll_ui)

    # ---------------- HELPERS / CLOSE ----------------
    def _on_close(self):
        self._closing = True
        if self._ui_update_after:
            try:
                self.after_cancel(self._ui_update_after)
            except Exception:
                pass

        # Persist session so next launch restores playlist, track, volume, mode, window position, sidebar width, opacity, autostart
        try:
            last_track_path = self.current_track.path if self.current_track else None
            geometry = self.geometry()
            self.manager.save_app_state(
                last_playlist_name=self.current_playlist_name,
                last_track_path=last_track_path,
                volume=self.audio.get_volume(),
                play_mode=self._play_mode,
                window_geometry=geometry,
                sidebar_width=getattr(self, "_sidebar_width", 260),
                opacity=getattr(self, "_opacity", 1.0),
                autostart=getattr(self, "_autostart", False),
            )
        except Exception:
            pass

        self.audio.cleanup()
        self.manager.save()

        # Stop media key listener
        if hasattr(self, '_media_listener') and self._media_listener:
            try:
                self._media_listener.stop()
            except Exception:
                pass

        self.destroy()

    # Keyboard shortcuts (bound to root)
    def _bind_keys(self):
        # already can add more
        self.bind("<space>", lambda e: self._toggle_play())
        self.bind("<Left>", lambda e: self._seek_relative(-5))
        self.bind("<Right>", lambda e: self._seek_relative(5))
        self.bind("<Control-Left>", lambda e: self._prev_track())
        self.bind("<Control-Right>", lambda e: self._next_track())

    def _start_media_key_listener(self):
        """Start global listener for media keys (play/pause, next track, previous track).
        This allows controlling the player with keyboard media buttons (fn+f5/f6/f7 or dedicated keys)
        even when the app window is not focused, similar to Spotify/YouTube/VK.
        """
        try:
            from pynput import keyboard

            def on_press(key):
                try:
                    if key == keyboard.Key.media_play_pause:
                        self.after(0, self._toggle_play)
                    elif key == keyboard.Key.media_next:
                        self.after(0, self._next_track)
                    elif key == keyboard.Key.media_previous:
                        self.after(0, self._prev_track)
                    # Optional: volume keys could adjust self.audio.set_volume, but not requested
                except Exception:
                    pass  # ignore if app is closing etc.

            self._media_listener = keyboard.Listener(on_press=on_press)
            self._media_listener.start()
        except Exception as e:
            # pynput not installed or hook failed (e.g. permissions) - app still works without global keys
            print(f"[MediaKeys] Could not start global media key listener: {e}")
            self._media_listener = None

    def _seek_relative(self, delta: float):
        if self.current_track:
            pos = self.audio.get_pos() + delta
            self._seek_to(max(0, pos))

    def _restore_last_session(self):
        """Restore last used playlist, track, volume and play mode from previous run."""
        state = self.manager.load_app_state()
        if not state:
            # default: open first playlist
            if self.manager.playlists:
                self._open_playlist(self.manager.playlists[0].name)
            return

        last_pl = state.get("last_playlist_name")
        last_track_path = state.get("last_track_path")
        vol = float(state.get("volume", 0.7))
        mode = state.get("play_mode")

        # Apply volume immediately
        self.audio.set_volume(max(0.0, min(1.0, vol)))
        if hasattr(self, "now_panel") and hasattr(self.now_panel, "vol_var"):
            self.now_panel.vol_var.set(self.audio.get_volume())

        if last_pl:
            pl = self.manager.get_playlist(last_pl)
            if pl:
                self._open_playlist(last_pl)

                # Try to restore the exact last track (highlight + load paused)
                if last_track_path:
                    for i, t in enumerate(pl.tracks):
                        if t.path == last_track_path:
                            self.current_track_idx = i
                            self.current_track = t
                            if self.audio.load(t.path):
                                self.audio.set_length(getattr(t, "duration", 0.0) or 0.0)
                            self._highlight_current_row()
                            self._show_or_update_now_panel()
                            break

        self._play_mode = mode

    # ---------------- SASH (resizable divider - place based for smooth non-jerky drag, no artifacts) ----------------
    def _place_sash(self):
        """Position the sash at the right edge of the sidebar. Called after layout and on resizes.
        Uses sidebar height for reliability (avoids status bar)."""
        if not hasattr(self, "sash") or self.sash is None:
            return
        try:
            self.update_idletasks()
            sx = max(0, int(self.sidebar.winfo_width()))
            sh = max(200, int(self.sidebar.winfo_height()))
            self.sash.place(x=sx, y=0, width=5, height=sh)
            self.sash.lift()
        except Exception:
            # Last resort: make it visible with safe values
            try:
                self.sash.place(x=260, y=0, width=5, height=500)
                self.sash.lift()
            except Exception:
                pass

    def _on_sash_press(self, event):
        self._sash_dragging = True
        self._sash_drag_start_x = event.x_root
        try:
            self._sash_drag_start_w = int(self.sidebar.cget("width"))
        except Exception:
            self._sash_drag_start_w = getattr(self, "_sidebar_width", 260)

    def _on_sash_drag(self, event):
        if not hasattr(self, "_sash_drag_start_x") or not self._sash_dragging:
            return
        delta = event.x_root - self._sash_drag_start_x
        new_w = self._sash_drag_start_w + delta

        # Reasonable bounds + leave enough room on right for tracks/controls (prevents "only two positions" snap)
        min_left = 160
        min_right = 480
        max_left = max(min_left, self.winfo_width() - min_right)
        new_w = max(min_left, min(max_left, new_w))

        self.sidebar.configure(width=new_w)
        self._sidebar_width = new_w

        # Move sash live
        try:
            self.sash.place(x=new_w)
        except Exception:
            pass

        # Force layout pass immediately — this removes jerk and right-side artifacts
        self.update_idletasks()

    def _on_sash_release(self, event):
        self._sash_dragging = False
        # Final position + place sash cleanly
        try:
            self._place_sash()
        except Exception:
            pass
        # Optional: could persist sidebar immediately here, but save on close is sufficient and cheaper

    # ---------------- SETTINGS (gear toggle, on the RIGHT in tracks area) ----------------
    def _toggle_settings(self):
        if getattr(self, "_settings_open", False):
            self._close_settings()
        else:
            self._open_settings()

    def _open_settings(self):
        if self.settings_frame is None:
            self._create_settings_panel()
        self._settings_open = True
        self._position_settings_panel()
        try:
            self.settings_frame.lift()
        except Exception:
            pass

    def _close_settings(self):
        if self.settings_frame is not None:
            try:
                self.settings_frame.place_forget()
            except Exception:
                pass
        self._settings_open = False

    def _create_settings_panel(self):
        # Created as child of tracks_container so we can place it precisely over the tracks list area
        self.settings_frame = ctk.CTkFrame(
            self.tracks_container, fg_color=BG_OVERLAY, border_color=ACCENT_FRAME, border_width=1, corner_radius=0
        )

        pad = 14
        # Title
        ctk.CTkLabel(
            self.settings_frame, text="Настройки",
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=pad, pady=(12, 6))

        # Thin accent line
        ctk.CTkFrame(self.settings_frame, height=1, fg_color=ACCENT_FRAME).pack(fill="x", padx=pad, pady=(0, 8))

        # 1) Autostart
        self.autostart_var = ctk.BooleanVar(value=self._autostart)
        sw = ctk.CTkSwitch(
            self.settings_frame,
            text="Автозапуск при включении ПК",
            variable=self.autostart_var,
            command=self._on_autostart_changed,
            progress_color=ACCENT_GLOW,
            button_color=ACCENT_GLOW,
            text_color=TEXT_PRIMARY
        )
        sw.pack(anchor="w", padx=pad, pady=6)

        # 2) Opacity (slider + % like volume)
        ctk.CTkLabel(
            self.settings_frame, text="Непрозрачность окна",
            text_color=TEXT_SECONDARY, font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=pad, pady=(8, 2))

        op_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        op_frame.pack(fill="x", padx=pad, pady=2)

        self.opacity_var = ctk.DoubleVar(value=self._opacity)
        self.opacity_slider = ctk.CTkSlider(
            op_frame, from_=0.1, to=1.0, variable=self.opacity_var,
            width=210, height=14, button_length=12,
            button_color=ACCENT_GLOW, progress_color=ACCENT_GLOW,
            command=self._on_opacity_slider
        )
        self.opacity_slider.pack(side="left", padx=(0, 8))

        self.opacity_pct = ctk.CTkLabel(
            op_frame, text=f"{int(self._opacity * 100)}%", text_color=TEXT_PRIMARY, width=48
        )
        self.opacity_pct.pack(side="left")

        # The rest of settings space is intentionally left empty for future options (per original request)
        filler = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        filler.pack(fill="both", expand=True)

        # Explicit bottom accent line so the light-blue border fully encloses the entire settings panel
        # (top + left + right + bottom). Without this the bottom border could appear missing visually.
        ctk.CTkFrame(self.settings_frame, height=1, fg_color=ACCENT_FRAME).pack(fill="x", padx=0, pady=0)

        # NO "Закрыть" button — toggle only via gear (as requested)

    def _position_settings_panel(self):
        """Place the settings panel on the RIGHT (over tracks list).
        Width: matches the top action buttons group width (gear+play+random+sources) or left edge of gear.
        Height: from below top bar all the way down to (touching) the now-playing bottom panel.
        Opens immediately thanks to repeated idletasks."""
        if self.settings_frame is None:
            return
        try:
            # Multiple forced layouts so sizes are accurate on first click
            for _ in range(3):
                self.update_idletasks()
                self.tracks_container.update_idletasks()
                self.now_panel.update_idletasks()
                if hasattr(self, 'top_actions_frame'):
                    self.top_actions_frame.update_idletasks()

            c_w = self.tracks_container.winfo_width()
            now_y = 0
            try:
                now_y = int(self.now_panel.winfo_y())
            except Exception:
                now_y = self.tracks_container.winfo_height() - 90

            # Height must reach / touch the lower now-playing panel
            settings_h = max(140, now_y + 3)  # +3 to ensure the bottom border visually touches the panel

            # Width: sum / span of the top buttons (as user requested "суммарно как все кнопки вверху")
            # Positioned so left edge aligns with left of the leftmost (gear)
            settings_w = 420  # safe fallback
            try:
                if hasattr(self, 'top_actions_frame') and self.top_actions_frame:
                    actions_w = max(200, int(self.top_actions_frame.winfo_width()))
                    settings_w = max(280, actions_w)
                else:
                    # fallback: sum button widths + paddings (gear is leftmost)
                    gw = int(getattr(self, 'btn_gear', None).winfo_width()) if getattr(self, 'btn_gear', None) else 34
                    pw = int(getattr(self, 'btn_play', None).winfo_width()) if getattr(self, 'btn_play', None) else 140
                    rw = int(getattr(self, 'btn_random', None).winfo_width()) if getattr(self, 'btn_random', None) else 140
                    sw = int(getattr(self, 'btn_sources', None).winfo_width()) if getattr(self, 'btn_sources', None) else 170
                    settings_w = max(280, gw + pw + rw + sw + 20)
            except Exception:
                pass

            # Right-align under the buttons group so left of panel ~ left of gear
            settings_x = max(0, c_w - settings_w)

            self.settings_frame.place(in_=self.tracks_container, x=settings_x, y=0, width=settings_w, height=settings_h)
            self.settings_frame.lift()
        except Exception:
            # Last resort full-ish right panel
            try:
                self.settings_frame.place(in_=self.tracks_container, x=0, y=0, relwidth=0.6, relheight=0.8)
                self.settings_frame.lift()
            except Exception:
                pass

    def _on_autostart_changed(self):
        self._autostart = bool(self.autostart_var.get())
        self._apply_autostart()

    def _on_opacity_slider(self, val: float):
        val = max(0.1, min(1.0, float(val)))
        self._opacity = val
        try:
            self.attributes("-alpha", val)
        except Exception:
            pass
        if hasattr(self, "opacity_pct") and self.opacity_pct and self.opacity_pct.winfo_exists():
            self.opacity_pct.configure(text=f"{int(val * 100)}%")

    def _apply_autostart(self):
        """Create or remove Startup folder shortcut for autostart on boot (default off)."""
        try:
            import winshell
            startup = winshell.startup()
            lnk_path = os.path.join(startup, "MolPlayer.lnk")
            if self._autostart:
                if getattr(sys, "frozen", False):
                    target = sys.executable
                    with winshell.shortcut(lnk_path) as sc:
                        sc.path = target
                        try:
                            sc.working_directory = os.path.dirname(target)
                        except Exception:
                            pass
                        sc.description = "MolPlayer"
                else:
                    try:
                        self.status.configure(text="Автозапуск: доступен после сборки .exe (portable/installer)")
                    except Exception:
                        pass
                    return
            else:
                if os.path.exists(lnk_path):
                    try:
                        os.remove(lnk_path)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Autostart] {e}")

    # ---------------- Configure handler: reposition sash + settings panel on window resize (when not dragging) ----------------
    def _on_window_configure(self, event=None):
        if event is None or event.widget is not self:
            return
        # Always try to keep sash positioned (unless actively dragging)
        if not getattr(self, "_sash_dragging", False):
            try:
                self._place_sash()
            except Exception:
                pass
        # If settings open (now on right), re-calc its size/position
        if getattr(self, "_settings_open", False) and self.settings_frame and self.settings_frame.winfo_exists():
            try:
                self._position_settings_panel()
            except Exception:
                pass

    # ---------------- SOURCES MENU (dropdown from button) ----------------
    def _show_sources_menu(self):
        pl = self.manager.get_current()
        if not pl:
            return

        # Toggle: if already open, close it
        if hasattr(self, '_sources_popup') and self._sources_popup and self._sources_popup.winfo_exists():
            self._sources_popup.destroy()
            self._sources_popup = None
            return

        popup = ctk.CTkToplevel(self)
        popup.overrideredirect(True)  # borderless dropdown look
        popup.configure(fg_color=BG_PANEL)

        self._sources_popup = popup

        main_frame = ctk.CTkFrame(popup, fg_color=BG_PANEL)
        main_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Add folder at top
        add_btn = ctk.CTkButton(main_frame, text="📁 Добавить папку",
                                command=lambda: self._menu_add_folder(popup))
        add_btn.pack(fill="x", pady=(0, 4))

        if pl.folders:
            for folder in pl.folders:
                row = ctk.CTkFrame(main_frame, fg_color=BG_TRACK)
                row.pack(fill="x", pady=1)

                display = folder if len(folder) <= 50 else "..." + folder[-47:]
                lbl = ctk.CTkLabel(row, text=display, anchor="w", text_color=TEXT_PRIMARY)
                lbl.pack(side="left", fill="x", expand=True, padx=4, pady=2)

                rem = ctk.CTkButton(row, text="✕", width=22, height=20,
                                    fg_color=BTN_BG, hover_color=BTN_HOVER,
                                    command=lambda f=folder: self._menu_remove_folder(f, popup))
                rem.pack(side="right", padx=3)

            # Delete all
            del_all = ctk.CTkButton(main_frame, text="🗑 Удалить все папки",
                                    fg_color="#3A2A2A", hover_color="#4A2A2A",
                                    command=lambda: self._menu_remove_all(popup))
            del_all.pack(fill="x", pady=(4, 0))
        else:
            ctk.CTkLabel(main_frame, text="Нет добавленных папок",
                         text_color=TEXT_MUTED).pack(pady=6)

        # Now that content is built, calculate dynamic height to fit exactly the content
        popup.update_idletasks()
        req_height = main_frame.winfo_reqheight() + 8  # small padding
        # Width approx sum of "Случайно" + "Источники плейлиста" buttons
        try:
            btn = self.btn_sources
            random_btn = getattr(self, 'btn_random', None)
            rw = random_btn.winfo_width() if random_btn else 140
            sw = btn.winfo_width() if btn else 170
            popup_w = rw + sw + 10
            popup_x = btn.winfo_rootx() - rw   # align to span random + sources horizontally
            popup_y = btn.winfo_rooty() + btn.winfo_height()
            popup.geometry(f"{popup_w}x{req_height}+{popup_x}+{popup_y}")
        except Exception:
            popup.geometry(f"320x{req_height}")

    def _menu_add_folder(self, popup):
        popup.destroy()
        self._sources_popup = None
        self._add_folder_to_current()

    def _menu_remove_folder(self, folder, popup):
        popup.destroy()
        self._sources_popup = None
        if self.current_playlist_name and self.manager.remove_folder(self.current_playlist_name, folder):
            self._refresh_tracks_list()
            pl = self.manager.get_current()
            self.play_order = list(range(len(pl.tracks))) if pl else []
            if self.current_track and str(Path(self.current_track.path).resolve()).startswith(str(Path(folder).resolve())):
                self._stop_playback()
                self.current_track = None
                self.current_track_idx = None
                self._hide_now_panel()

    def _menu_remove_all(self, popup):
        popup.destroy()
        self._sources_popup = None
        pl = self.manager.get_current()
        if pl and pl.folders:
            pl.folders = []
            pl.tracks = []  # disconnecting sources clears the playlist's tracks
            self.manager.save()
            self._refresh_tracks_list()
            self.play_order = []
            self._stop_playback()
            self.current_track = None
            self.current_track_idx = None
            self._hide_now_panel()

    # ---------------- UPDATES ----------------
    def _check_for_updates(self, silent: bool = False):
        """Check GitHub Releases for a newer version and offer in-app update.
        When silent=True: only shows a dialog if a real update is available.
        Never shows "you are on latest" or error popups in silent mode.
        """
        try:
            api_url = "https://api.github.com/repos/Granik115/MolPlayer/releases/latest"
            req = urllib.request.Request(api_url, headers={"User-Agent": "MolPlayer-Updater/0.5"})

            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as http_err:
                if http_err.code == 404:
                    # No releases yet — silently ignore in silent mode
                    if not silent:
                        messagebox.showinfo(
                            "Обновления",
                            "На GitHub пока нет опубликованных релизов.\n\n"
                            "Чтобы авто-обновления заработали, создай хотя бы один Release "
                            "и загрузи в него MolPlayer-portable.zip."
                        )
                    return
                # Other HTTP errors — silent in silent mode
                if not silent:
                    messagebox.showerror("Ошибка обновления", f"Не удалось связаться с GitHub: {http_err}")
                return

            latest_tag = data.get("tag_name", "v0.0.0")

            # Find best asset
            asset_url = None
            assets = data.get("assets", [])
            for asset in assets:
                name = asset.get("name", "")
                if "portable" in name.lower() and name.endswith(".zip"):
                    asset_url = asset.get("browser_download_url")
                    break
            if not asset_url:
                for asset in assets:
                    if asset.get("name", "").endswith(".zip"):
                        asset_url = asset.get("browser_download_url")
                        break

            if not asset_url:
                if not silent:
                    messagebox.showinfo("Обновления", "В последнем релизе не найдено подходящего архива.")
                return

            current_ver = self._ver_tuple(APP_VERSION)
            latest_ver = self._ver_tuple(latest_tag)

            if latest_ver <= current_ver:
                # No newer version — stay completely silent when in silent mode
                if not silent:
                    messagebox.showinfo("Обновления", f"У вас уже последняя версия ({APP_VERSION}).")
                return

            # There is a real update — even in silent mode we can show the offer
            if messagebox.askyesno(
                "Доступно обновление",
                f"Доступна новая версия {latest_tag} (у вас {APP_VERSION}).\n\n"
                "Загрузить и установить обновление сейчас?\n"
                "Приложение автоматически перезапустится после обновления."
            ):
                self._perform_self_update(asset_url, latest_tag)

        except Exception as e:
            # In silent mode we never bother the user with errors
            if not silent:
                messagebox.showerror("Ошибка обновления", f"Не удалось проверить обновления:\n{e}")

    def _perform_self_update(self, download_url: str, new_version_tag: str):
        """Download the zip in background, prepare updater .bat and restart the app."""
        progress_win = ctk.CTkToplevel(self)
        progress_win.title("Обновление MolPlayer")
        progress_win.geometry("340x130")
        progress_win.resizable(False, False)
        ctk.CTkLabel(progress_win, text=f"Загрузка {new_version_tag}...").pack(pady=(12, 4))
        pbar = ctk.CTkProgressBar(progress_win, width=280)
        pbar.pack(pady=4)
        pbar.set(0.0)
        lbl = ctk.CTkLabel(progress_win, text="0%")
        lbl.pack()

        def worker():
            try:
                tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip").name
                def hook(blocknum, blocksize, totalsize):
                    if totalsize > 0:
                        frac = min(blocknum * blocksize / totalsize, 1.0)
                        self.after(0, lambda f=frac: (pbar.set(f), lbl.configure(text=f"{int(f*100)}%")))
                urllib.request.urlretrieve(download_url, tmp_zip, reporthook=hook)

                extract_dir = tempfile.mkdtemp(prefix="mol_upd_")
                with zipfile.ZipFile(tmp_zip, "r") as zf:
                    zf.extractall(extract_dir)

                # zip usually contains MolPlayer/ subfolder
                src_dir = os.path.join(extract_dir, "MolPlayer")
                if not os.path.isdir(src_dir):
                    src_dir = extract_dir

                # Determine current application directory
                if getattr(sys, "frozen", False):
                    app_dir = os.path.dirname(sys.executable)
                else:
                    app_dir = os.path.dirname(os.path.abspath(__file__))

                # Create a self-deleting updater batch
                bat = os.path.join(tempfile.gettempdir(), "molplayer_updater.bat")
                bat_src = src_dir.replace("\\", "\\\\")
                app_src = app_dir.replace("\\", "\\\\")
                bat_content = f"""@echo off
chcp 65001 >nul
timeout /t 2 /nobreak >nul
echo Применение обновления MolPlayer...
robocopy "{bat_src}" "{app_src}" /E /R:3 /W:1 /NFL /NDL /NJH /NJS
start "" "{app_src}\\MolPlayer.exe"
rd /s /q "{extract_dir}" >nul 2>&1
del "%~f0" >nul 2>&1
"""
                with open(bat, "w", encoding="cp866") as f:
                    f.write(bat_content)

                self.after(0, progress_win.destroy)
                self.after(150, lambda: self._launch_updater_and_exit(bat))
            except Exception as ex:
                self.after(0, lambda: (progress_win.destroy(),
                                       messagebox.showerror("Ошибка обновления", f"Не удалось установить обновление:\n{ex}")))

        threading.Thread(target=worker, daemon=True).start()

    def _launch_updater_and_exit(self, bat_path: str):
        try:
            # Launch detached
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(["cmd", "/c", bat_path], shell=True, creationflags=CREATE_NO_WINDOW)
        except Exception:
            subprocess.Popen(bat_path, shell=True)
        self.destroy()

    # ---------------- ROLLBACK TO PREVIOUS VERSION ----------------
    def _show_rollback_versions(self):
        """Show list of previous versions available on GitHub (portable zips) for rollback.
        Placed next to the "Обновления" button."""
        # Toggle: close if already open
        if hasattr(self, '_rollback_popup') and self._rollback_popup and self._rollback_popup.winfo_exists():
            self._rollback_popup.destroy()
            self._rollback_popup = None
            return

        try:
            api_url = "https://api.github.com/repos/Granik115/MolPlayer/releases"
            req = urllib.request.Request(api_url, headers={"User-Agent": "MolPlayer-Updater/1.0"})

            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    releases = _json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as http_err:
                if http_err.code == 404:
                    messagebox.showinfo("Откат версии", "На GitHub пока нет опубликованных релизов.")
                    return
                messagebox.showerror("Ошибка отката", f"Не удалось связаться с GitHub: {http_err}")
                return

            current_ver = self._ver_tuple(APP_VERSION)
            candidates = []
            for rel in releases:
                tag = rel.get("tag_name", "")
                if not tag:
                    continue
                tver = self._ver_tuple(tag)
                if tver >= current_ver:
                    continue  # only older versions for rollback
                asset_url = None
                for asset in rel.get("assets", []):
                    name = asset.get("name", "")
                    if "portable" in name.lower() and name.endswith(".zip"):
                        asset_url = asset.get("browser_download_url")
                        break
                if asset_url:
                    candidates.append((tag, asset_url))

            if not candidates:
                messagebox.showinfo("Откат версии", "Нет доступных предыдущих версий с portable-архивом.")
                return

            # Sort by version descending (newest previous first)
            candidates.sort(key=lambda c: self._ver_tuple(c[0]), reverse=True)

            # Popup similar to sources menu
            popup = ctk.CTkToplevel(self)
            popup.overrideredirect(True)
            popup.configure(fg_color=BG_PANEL)
            self._rollback_popup = popup

            main_frame = ctk.CTkFrame(popup, fg_color=BG_PANEL)
            main_frame.pack(fill="both", expand=True, padx=4, pady=4)

            ctk.CTkLabel(main_frame, text="Откат на предыдущую версию",
                         text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=12, weight="bold")).pack(pady=(0, 4))

            for tag, url in candidates[:10]:  # limit list
                btn = ctk.CTkButton(
                    main_frame, text=f"↩ {tag}",
                    fg_color=BTN_BG, hover_color=BTN_HOVER,
                    text_color=TEXT_PRIMARY,
                    command=lambda u=url, t=tag, p=popup: self._do_rollback(u, t, p)
                )
                btn.pack(fill="x", pady=1)

            ctk.CTkLabel(main_frame, text="Выберите версию для отката",
                         text_color=TEXT_MUTED, font=ctk.CTkFont(size=10)).pack(pady=(4, 0))

            # Position near the rollback / updates buttons (bottom of sidebar)
            popup.update_idletasks()
            try:
                ref_btn = getattr(self, 'btn_rollback', self.btn_check_updates)
                req_h = main_frame.winfo_reqheight() + 8
                popup_w = 210
                popup_x = ref_btn.winfo_rootx() - 60
                popup_y = ref_btn.winfo_rooty() + ref_btn.winfo_height() + 2
                popup.geometry(f"{popup_w}x{req_h}+{popup_x}+{popup_y}")
            except Exception:
                popup.geometry(f"210x{min(240, 30 + len(candidates)*26)}")

        except Exception as e:
            messagebox.showerror("Ошибка отката", f"Не удалось получить список версий:\n{e}")
            if hasattr(self, '_rollback_popup') and self._rollback_popup:
                try:
                    self._rollback_popup.destroy()
                except:
                    pass
            self._rollback_popup = None

    def _ver_tuple(self, v: str):
        v = v.lstrip("vV")
        try:
            return tuple(int(x) for x in v.split(".")[:3])
        except Exception:
            return (0, 0, 0)

    def _do_rollback(self, asset_url: str, tag: str, popup):
        popup.destroy()
        self._rollback_popup = None

        if not messagebox.askyesno(
            "Подтверждение отката",
            f"Откатиться на {tag}?\n\n"
            "Файлы приложения будут заменены на версию из архива.\n"
            "Приложение автоматически перезапустится."
        ):
            return

        # Reuse the exact same self-update mechanism (works for older versions too)
        self._perform_self_update(asset_url, tag)

def main():
    # Ensure pygame mixer is happy on some systems
    try:
        # already inited in AudioEngine
        pass
    except Exception:
        pass

    app = MolPlayerApp()
    app._bind_keys()  # after init
    app.mainloop()


if __name__ == "__main__":
    main()
