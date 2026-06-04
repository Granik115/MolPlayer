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

# Local
from constants import (
    BG_DARK, BG_SIDEBAR, BG_PANEL, BG_TRACK, BG_TRACK_HOVER, BG_TRACK_SELECTED,
    BG_OVERLAY,
    ACCENT_BLUE, ACCENT_BLUE_HOVER, ACCENT_CYAN, ACCENT_CYAN_HOVER,
    ACCENT_GLOW, ACCENT_GLOW_TEAL, DEPTH_BLUE, BTN_PRIMARY, BTN_PRIMARY_HOVER,
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

        # Bind clicks
        for w in (self, self.lbl_num, self.lbl_name, self.lbl_dur):
            w.bind("<Button-1>", self._on_click)
            w.bind("<Double-Button-1>", self._on_double)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _=None):
        if not self._selected:
            self.configure(fg_color=BG_TRACK_HOVER)

    def _on_leave(self, _=None):
        if not self._selected:
            self.configure(fg_color=BG_TRACK)

    def set_selected(self, sel: bool):
        self._selected = sel
        self._apply_color()

    def set_playing(self, playing: bool):
        self._playing = playing
        self._apply_color()

    def _apply_color(self):
        if getattr(self, "_playing", False):
            self.configure(fg_color=DEPTH_BLUE)  # deep blue for currently playing row (from reference)
            self.lbl_num.configure(text_color=ACCENT_GLOW)
        elif self._selected:
            self.configure(fg_color=BG_TRACK_SELECTED)
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

        # Layout
        self.grid_columnconfigure(1, weight=1)

        # Top row: title + close
        self.lbl_title = ctk.CTkLabel(
            self, text="Нет воспроизведения", anchor="w",
            text_color=TEXT_PRIMARY, font=ctk.CTkFont(size=12, weight="bold")
        )
        self.lbl_title.grid(row=0, column=0, columnspan=4, padx=10, pady=(6, 2), sticky="ew")

        # Progress row
        self.progress_var = ctk.DoubleVar(value=0.0)
        self.progress = ctk.CTkSlider(
            self, from_=0, to=1, variable=self.progress_var,
            button_color=ACCENT_GLOW, button_hover_color=ACCENT_GLOW_TEAL,
            progress_color=ACCENT_GLOW, fg_color=PROGRESS_BG,
            height=8, command=self._on_seek_slider
        )
        self.progress.grid(row=1, column=0, columnspan=4, padx=10, pady=(2, 4), sticky="ew")

        # Time labels
        self.lbl_time = ctk.CTkLabel(self, text="0:00 / 0:00", text_color=TEXT_MUTED, font=ctk.CTkFont(size=10))
        self.lbl_time.grid(row=2, column=0, padx=10, pady=(0, 6), sticky="w")

        # Controls
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=2, column=1, columnspan=3, padx=4, pady=(0, 6), sticky="e")

        # Buttons
        self.btn_prev = ctk.CTkButton(ctrl_frame, text="⏮", width=32, height=28,
                                      fg_color=BTN_BG, hover_color=BTN_HOVER,
                                      command=self.on_prev)
        self.btn_prev.pack(side="left", padx=2)

        self.btn_toggle = ctk.CTkButton(ctrl_frame, text="▶", width=36, height=28,
                                        fg_color=ACCENT_GLOW, hover_color=ACCENT_GLOW_TEAL,
                                        text_color="black", font=ctk.CTkFont(weight="bold"),
                                        command=self.on_toggle)
        self.btn_toggle.pack(side="left", padx=2)

        self.btn_next = ctk.CTkButton(ctrl_frame, text="⏭", width=32, height=28,
                                      fg_color=BTN_BG, hover_color=BTN_HOVER,
                                      command=self.on_next)
        self.btn_next.pack(side="left", padx=2)

        # Volume
        self.vol_var = ctk.DoubleVar(value=self.audio.get_volume())
        self.vol_slider = ctk.CTkSlider(
            ctrl_frame, from_=0, to=1, variable=self.vol_var,
            width=70, height=14, button_length=12,
            button_color=ACCENT_GLOW, progress_color=ACCENT_GLOW,
            command=self._on_vol_change
        )
        self.vol_slider.pack(side="left", padx=(8, 4))

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
            self.btn_toggle.configure(text="▶", fg_color=ACCENT_CYAN)
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
            self.btn_toggle.configure(text="⏸", fg_color=DEPTH_BLUE)  # deep blue for "playing" state
        elif is_paused:
            self.btn_toggle.configure(text="▶", fg_color=ACCENT_GLOW)
        else:
            self.btn_toggle.configure(text="▶", fg_color=ACCENT_GLOW)

    def set_dragging(self, d: bool):
        self._dragging_seek = d


class MolPlayerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — {APP_VERSION}")
        self.geometry("1100x680")
        self.minsize(900, 560)

        # Slight transparency so desktop / other windows bleed through (Win10/11)
        # Adjust 0.90 - 0.96 for taste. Makes the sci-fi machine "float".
        try:
            self.attributes("-alpha", 0.93)
        except Exception:
            pass  # some platforms may not support

        # State
        self.manager = PlaylistManager()
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

        # Try to restore last open playlist if any
        if self.manager.playlists:
            self._open_playlist(self.manager.playlists[0].name)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- UI BUILD ----------------
    def _build_ui(self):
        self.configure(fg_color=BG_DARK)

        # Main grid: left sidebar | right content
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # LEFT: Playlists sidebar
        self.sidebar = ctk.CTkFrame(self, fg_color=BG_SIDEBAR, width=260, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Sidebar header
        hdr = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(12, 6))

        ctk.CTkLabel(hdr, text="ПЛЕЙЛИСТЫ", text_color=TEXT_SECONDARY,
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")

        self.btn_new_pl = ctk.CTkButton(
            hdr, text="+", width=32, height=28,
            fg_color=BTN_PRIMARY, hover_color=BTN_PRIMARY_HOVER,
            text_color="white", font=ctk.CTkFont(size=16, weight="bold"),
            command=self._create_new_playlist
        )
        self.btn_new_pl.pack(side="right")

        # Scrollable playlists
        self.pl_scroll = ctk.CTkScrollableFrame(self.sidebar, fg_color=BG_SIDEBAR, label_text="")
        self.pl_scroll.pack(fill="both", expand=True, padx=6, pady=4)

        self.pl_buttons: List[ctk.CTkButton] = []

        # Bottom sidebar actions
        bot = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bot.pack(fill="x", padx=8, pady=8)
        self.btn_del_pl = ctk.CTkButton(
            bot, text="Удалить плейлист", fg_color="#3A2A2A", hover_color="#4A2A2A",
            text_color=TEXT_PRIMARY, command=self._delete_current_playlist
        )
        self.btn_del_pl.pack(fill="x")

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

        self.btn_play = ctk.CTkButton(
            actions, text="▶ Воспроизвести", width=140, height=32,
            fg_color=BTN_PRIMARY, hover_color=BTN_PRIMARY_HOVER,
            text_color="white", font=ctk.CTkFont(weight="bold"),
            command=lambda: self._play_playlist(start_random=False)
        )
        self.btn_play.pack(side="left", padx=3)

        self.btn_random = ctk.CTkButton(
            actions, text="🎲 Случайно", width=110, height=32,
            fg_color=ACCENT_CYAN, hover_color=ACCENT_CYAN_HOVER,
            text_color="black", font=ctk.CTkFont(weight="bold"),
            command=lambda: self._play_playlist(start_random=True)
        )
        self.btn_random.pack(side="left", padx=3)

        self.btn_add_folder = ctk.CTkButton(
            actions, text="📁 Добавить папку", width=130, height=32,
            fg_color=BTN_PRIMARY, hover_color=BTN_PRIMARY_HOVER,
            text_color="white",
            command=self._add_folder_to_current
        )
        self.btn_add_folder.pack(side="left", padx=3)

        self.btn_clear = ctk.CTkButton(
            actions, text="🗑 Очистить", width=90, height=32,
            fg_color=BTN_BG, hover_color=BTN_HOVER,
            text_color=TEXT_PRIMARY,
            command=self._clear_current_playlist
        )
        self.btn_clear.pack(side="left", padx=3)

        # TRACKS AREA: list on top (most space), full-width now-playing bar at bottom
        self.tracks_container = ctk.CTkFrame(self.content, fg_color=BG_PANEL)
        self.tracks_container.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.tracks_container.grid_columnconfigure(0, weight=1)
        self.tracks_container.grid_rowconfigure(0, weight=1)   # tracks list expands
        self.tracks_container.grid_rowconfigure(1, weight=0)   # now playing bar fixed

        self.tracks_scroll = ctk.CTkScrollableFrame(
            self.tracks_container, fg_color=BG_PANEL, label_text=""
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
        self.audio.cleanup()
        self.manager.save()
        self.destroy()

    # Keyboard shortcuts (bound to root)
    def _bind_keys(self):
        # already can add more
        self.bind("<space>", lambda e: self._toggle_play())
        self.bind("<Left>", lambda e: self._seek_relative(-5))
        self.bind("<Right>", lambda e: self._seek_relative(5))
        self.bind("<Control-Left>", lambda e: self._prev_track())
        self.bind("<Control-Right>", lambda e: self._next_track())

    def _seek_relative(self, delta: float):
        if self.current_track:
            pos = self.audio.get_pos() + delta
            self._seek_to(max(0, pos))


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
