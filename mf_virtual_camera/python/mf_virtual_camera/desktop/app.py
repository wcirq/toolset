from __future__ import annotations

import json
import sys
from pathlib import Path

from .plugin_host import validate_code


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) in (2, 4) and argv[0] == "--validate-plugin":
        code = Path(argv[1]).read_text(encoding="utf-8")
        payload = json.dumps(validate_code(code), ensure_ascii=True)
        if len(argv) == 4 and argv[2] == "--validation-result":
            Path(argv[3]).write_text(payload, encoding="utf-8")
        else:
            print(payload)
        return 0
    from PyQt5.QtWidgets import QApplication
    from .main_window import MainWindow
    app = QApplication([sys.argv[0], *argv]); app.setApplicationName("SSKJ Camera Studio")
    window = MainWindow(); window.show(); return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
