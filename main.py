import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import ZFN_GUI

def main():
    """
    应用程序主入口
    """
    app = QApplication(sys.argv)
    window = ZFN_GUI()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()