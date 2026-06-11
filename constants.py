"""
Constants and theme colors inspired by the "Промышленный молекулярный преобразователь" GUI screenshot.
Glowing blue/cyan accents (#3e80a3, #00bfff, #40e0d0), dark blue depth (#215175),
very dark blue-tinted backgrounds (#0f141b, #0a1a2e, #001a33).
Slight window transparency + unified button colors.
"""

# Audio formats we try to support
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".oga"}

# === Theme colors (MC Molecular Transformer inspired) ===
# Точные цвета из референса "Промышленный молекулярный преобразователь".
# Акцент: glowing blue/cyan #3e80a3 + #00bfff / #40e0d0
# Глубина: #215175
# Фон: очень тёмный с синим #0f141b / #0a1a2e / #001a33
# Сделано полупрозрачное окно + кнопки в похожей синей гамме.

# Glowing accent blue / cyan (рамки, обводка, подсветка, прогресс, glow)
ACCENT_FRAME = "#3e80a3"
ACCENT_FRAME_LIGHT = "#4181a7"
ACCENT_GLOW = "#00bfff"
ACCENT_GLOW_TEAL = "#40e0d0"
DEPTH_BLUE = "#215175"

# Очень тёмный фон (с синим оттенком)
BG_DARK = "#0f141b"
BG_SIDEBAR = "#0a111c"

# Тёмно-синие панели / overlay (как в референсе)
BG_PANEL = "#0a1a2e"
BG_OVERLAY = "#001a33"

# Track / slot backgrounds
BG_TRACK = "#12233a"
BG_TRACK_HOVER = "#18304f"
BG_TRACK_SELECTED = "#1e3a5f"

# Текст белый / светло-голубой
TEXT_PRIMARY = "#e8f4ff"
TEXT_SECONDARY = "#a8d4f0"
TEXT_MUTED = "#5c7a9a"

# Progress bar - glowing
PROGRESS_BG = "#1a2a47"
PROGRESS_FILL = "#00bfff"

# Кнопки - сделаны в похожей цветовой гамме (синий/голубой)
BTN_BG = "#215175"
BTN_HOVER = "#3e80a3"
BTN_PRIMARY = "#3e80a3"           # Play, Random и т.п. - основной glowing
BTN_PRIMARY_HOVER = "#00bfff"

# Borders
BORDER = "#215175"

# Status (ошибки минимально)
COLOR_ERROR = "#ff6b6b"
COLOR_SUCCESS = "#40e0d0"

# Aliases для совместимости со старым кодом (не удаляем старые имена)
ACCENT_BLUE = BTN_PRIMARY
ACCENT_BLUE_HOVER = BTN_PRIMARY_HOVER
ACCENT_CYAN = ACCENT_GLOW
ACCENT_CYAN_HOVER = ACCENT_GLOW_TEAL
PROGRESS_FILL_BLUE = ACCENT_FRAME
PROGRESS_FILL_CYAN = ACCENT_GLOW
ACCENT_BLUE_DARK = DEPTH_BLUE

# App info
APP_NAME = "MolPlayer"
APP_VERSION = "0.9.4"  # bump on releases
VERSION = APP_VERSION
