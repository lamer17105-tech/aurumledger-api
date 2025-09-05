# qt_check.py
import sys
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication(sys.argv)
QMessageBox.information(None, "PySide6 OK", "GUI 正常")
sys.exit(0)
