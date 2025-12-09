# main_app.py
import sys
from PySide6.QtWidgets import QApplication
from gui_widgets import MainWindowWidget

if __name__ == '__main__':
    # Initialise the application
    app = QApplication(sys.argv)
    # Call the main widget
    ex = MainWindowWidget()
    sys.exit(app.exec())