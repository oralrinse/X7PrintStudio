# -*- coding: utf-8 -*-
"""X7 图文打印工作室入口。"""
import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from x7printstudio.ui.mainwindow import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("X7 图文打印工作室")
    app.setOrganizationName("X7PrintStudio")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
