COLORS = {
    "bg": "#0B1020", "panel": "#121A2C", "panel2": "#172238",
    "text": "#EAF0FF", "muted": "#8EA0C0", "accent": "#50D5B7",
    "accent2": "#6C7CFF", "danger": "#FF6B7A", "border": "#273653",
}

STYLESHEET = """
* { font-family: "Microsoft YaHei UI"; font-size: 13px; color: #EAF0FF; }
QMainWindow, QWidget#root { background: #0B1020; }
QFrame#card { background: #121A2C; border: 1px solid #273653; border-radius: 14px; }
QLabel#title { font-size: 22px; font-weight: 700; }
QLabel#muted { color: #8EA0C0; }
QPushButton { background: #1B2942; border: 1px solid #304466; border-radius: 9px;
 padding: 9px 15px; font-weight: 600; }
QPushButton:hover { background: #243755; border-color: #50D5B7; }
QPushButton#primary { background: #50D5B7; color: #071512; border: none; }
QPushButton#danger { background: #3B1F2A; color: #FF93A0; border-color: #673040; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
 background: #0E1627; border: 1px solid #273653; border-radius: 8px; padding: 8px; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: #50D5B7; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: transparent; color: #8EA0C0; padding: 12px 18px; }
QTabBar::tab:selected { color: #50D5B7; border-bottom: 2px solid #50D5B7; }
QListWidget { background: transparent; border: none; }
QListWidget::item { background: #172238; border-radius: 8px; margin: 3px; padding: 10px; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #304466; border-radius: 4px; }
QMessageBox { background: #121A2C; }
QMessageBox QLabel { background: transparent; color: #EAF0FF; min-width: 420px; }
QMessageBox QPushButton { min-width: 88px; background: #1B2942; color: #EAF0FF;
 border: 1px solid #304466; border-radius: 7px; padding: 7px 12px; }
"""
