from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QTextEdit, QPushButton, QLineEdit, QListWidget, QCheckBox
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt
import time
import os
from ib_insync import *
import asyncio
# os.chdir(sys._MEIPASS)

class MainThread(QThread):
    """
    Runs a counter thread.
    """
    countChanged = pyqtSignal(str)

    def __init__(self, localh_host, port_num, trade_size, parent=None):
        QThread.__init__(self, parent)
        self.localh_host = localh_host
        self.port_num = port_num
        self.trade_size = trade_size

    def run(self):
        timer = 0
        home_dir = os.path.expanduser("~")
        filename = 'ib_order_data.csv'
        file_path = os.path.join(home_dir, filename)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ib = IB()
        ib.connect(self.localh_host, self.port_num, clientId=1)
        while True:
            try:
                if os.path.isfile(file_path):
                    f = open(file_path, "r")
                    result = f.read()
                    if result != '':
                        symbol = result.split(",")[0].split(":")[1]
                        side = result.split(",")[1].split(":")[1]
                        type = result.split(",")[2].split(":")[1]
                        # amount = result.split(",")[3].split(":")[1]
                        # price = result.split(",")[4].split(":")[1]
                        contract = Future(symbol)
                        bars = ib.reqContractDetails(contract)
                        contract = bars[0].contract
                        # if type == "MKT":
                        order = MarketOrder(side, int(self.trade_size))
                        # elif type == "LMT":
                        #     order = LimitOrder(side, int(self.trade_size), price)
                        trade = ib.placeOrder(contract, order)
                        time.sleep(1)
                        if "Trade" in str(trade):
                            str_temp = "  We've placed " + type + " " + side + " Order(Amount: " + str(self.trade_size) + ") for " + symbol
                        else:
                            str_temp = "  " + str(trade)
                        self.countChanged.emit(str_temp)
                        # str_temp = "  We've placed " + type + " Order(Amount: " + str(self.trade_size) + ") for " +
                        # symbol self.countChanged.emit(str_temp)
                        f = open(file_path, "w")
                        f.write('')
                        f.close()
                    else:
                        # if timer == 30:
                        self.countChanged.emit("  Please wait for a moment!")
                            # timer = 0
            except Exception as e:
                # ib.disconnect()
                print(e)
            # timer += 1
            time.sleep(10)

    def stop(self):
        self.terminate()


class MainWindow(QWidget):
    start_flag = 1

    def __init__(self):
        super(MainWindow, self).__init__()
        self.setGeometry(250, 50, 716, 458)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Robinhood Bot Panel")

        self.trade_size = 20
        self.backgroundLabel = QLabel(self)
        self.backgroundLabel.setGeometry(0, 0, 716, 458)
        self.backgroundLabel.setStyleSheet("background-image : url(IB_Bot_GUI.png); background-repeat: no-repeat;")
        font = QFont()
        font.setPointSize(20)
        self.closeBtn = QPushButton(self)
        self.closeBtn.setGeometry(680, 10, 29, 29)
        self.closeBtn.setStyleSheet("background-image : url(close2.png);background-color: transparent;")
        self.closeBtn.clicked.connect(self.onClose)

        self.optionBtn = QPushButton(self)
        self.optionBtn.setGeometry(405, 30, 41, 41)
        self.optionBtn.setStyleSheet("background-image : url(option.png);background-color: transparent;")
        self.optionBtn.clicked.connect(self.OpenSetting)

        self.startBtn = QPushButton(self)
        self.startBtn.setGeometry(465, 18, 200, 60)
        self.startBtn.setText("Start")
        self.startBtn.setStyleSheet("background-color: #db1222; border-radius: 8px; color:white; font-size:24px;")
        self.startBtn.clicked.connect(self.onStart)

        self.localhost = QLineEdit(self)
        self.localhost.setStyleSheet("background-color: transparent; border-radius: 15px; color:white; font-size:24px;")
        self.localhost.setGeometry(170, 117, 180, 24)
        self.localhost.setText("127.0.0.1")
        self.port = QLineEdit(self)
        self.port.setStyleSheet("background-color: transparent; border-radius: 15px; color:white; font-size:24px;")
        self.port.setGeometry(540, 117, 159, 24)
        self.port.setText("7497")
        self.listwidget = QListWidget(self)
        self.listwidget.setStyleSheet(
            "background-color: transparent; border-radius: 15px; color:white; font-size : 16px;")
        self.listwidget.setGeometry(25, 180, 665, 249)

    def onStart(self):
        if self.start_flag == 1:
            if self.localhost != '' and self.port != '':
                try:
                    self.main_thread = MainThread(localh_host=self.localhost.text(), port_num=int(self.port.text()), trade_size=self.trade_size)
                    self.main_thread.countChanged.connect(self.onProcess)
                    self.main_thread.start()
                    self.start_flag = 0
                    self.startBtn.setText("Stop")
                except Exception as e:
                    if "failed" in e:
                        print("Enter your correct Information")
            else:
                try:
                    if self.localhost == '':
                        self.TW = ThirdWindow("Please enter your host url!")
                        self.TW.show()
                    else:
                        self.TW = ThirdWindow("Please enter your port number!")
                        self.TW.show()
                except Exception as e:
                    print(e)
        else:
            self.startBtn.setText("Start")
            self.start_flag = 1
            self.listwidget.clear()
            self.main_thread.stop()

    def onClose(self):
        global app
        if self.start_flag == 0:
            self.main_thread.stop()
        app.quit()

    def on_toggle_password_Action(self):
        if not self.password_shown:
            self.password.setEchoMode(QLineEdit.Normal)
            self.password_shown = True
            self.password.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.password.setEchoMode(QLineEdit.Password)
            self.password_shown = False
            self.password.togglepasswordAction.setIcon(self.visibleIcon)

    def onProcess(self, value):
        self.listwidget.addItem(value)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.pos() - self.offset)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.offset = None
        super().mouseReleaseEvent(event)

    def SettingsUpdate(self, value):
        self.trade_size = int(value)
        print(self.trade_size)

    def OpenSetting(self):
        try:
            self.SW = SettingsWindow(str(self.trade_size))
            self.SW.countChanged.connect(self.SettingsUpdate)
            self.SW.show()
        except Exception as e:
            print(e)


class SettingsWindow(QWidget):
    countChanged = pyqtSignal(str)

    def __init__(self, trade_size):
        self.trade_size = trade_size
        super(SettingsWindow, self).__init__()

        self.setFixedSize(760, 600)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background:#0b0b0b;")
        self.titleText = QLabel(self)
        self.titleText.setText("Settings Page")
        self.titleText.setGeometry(80, 20, 200, 80)
        self.titleText.setStyleSheet("color:white; font-size:26px;border:none;")
        self.tradepercentLabel = QLabel(self)
        self.tradepercentLabel.setGeometry(40, 130, 150, 40)
        self.tradepercentLabel.setText("Trade Size:")
        self.tradepercentLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.tradepercentEdit = QLineEdit(self)
        self.tradepercentEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;")
        self.tradepercentEdit.setGeometry(180, 130, 150, 40)
        self.tradepercentEdit.setAlignment(Qt.AlignCenter)
        self.tradepercentEdit.setText(self.trade_size)
        self.confirmButton = QPushButton(self)
        self.confirmButton.setText("Save")
        self.confirmButton.setGeometry(80, 228, 200, 40)
        self.confirmButton.clicked.connect(self.OnShow)
        self.confirmButton.setStyleSheet("background:#db1222; border-radius:8px;color:white; font-size:16px;")
        self.closeBtn = QPushButton(self)
        self.closeBtn.setGeometry(360, 0, 20, 20)
        self.closeBtn.setStyleSheet("background-image : url(close3.png);background-color: transparent; ")
        self.closeBtn.clicked.connect(self.OnClose)

    def OnShow(self):
        self.countChanged.emit(self.tradepercentEdit.text())
        self.close()

    def OnClose(self):
        self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.pos() - self.offset)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.offset = None
        super().mouseReleaseEvent(event)


class SecondWindow(QWidget):
    countChanged = pyqtSignal(str)

    def __init__(self, value, data):
        self.data = data
        super(SecondWindow, self).__init__()
        self.header_text = value
        self.setFixedSize(380, 200)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background:#19181f;")
        self.titleText = QTextEdit(self)
        self.titleText.setText(self.header_text)
        self.titleText.setGeometry(20, 30, 340, 60)
        self.titleText.setStyleSheet("color:white; font-size:16px;border:none;")
        self.RequestCodeEdit = QLineEdit(self)
        self.RequestCodeEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;")
        self.RequestCodeEdit.setGeometry(20, 70, 340, 30)
        self.confirmButton = QPushButton(self)
        self.confirmButton.setText("Confirm")
        self.confirmButton.setGeometry(20, 128, 340, 40)
        self.confirmButton.clicked.connect(self.OnShow)
        self.confirmButton.setStyleSheet("background:#db1222; border-radius:8px;color:white; font-size:16px;")
        print(self.data)

    def OnShow(self):
        print("hello")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.pos() - self.offset)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.offset = None
        super().mouseReleaseEvent(event)


class ThirdWindow(QWidget):
    def __init__(self, data):
        super(ThirdWindow, self).__init__()
        self.header_text = data
        self.setFixedSize(280, 160)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background:#19181f;")
        self.titleText = QTextEdit(self)
        self.titleText.setText(self.header_text)
        self.titleText.setGeometry(20, 30, 240, 30)
        self.titleText.setStyleSheet("color:white; font-size:16px;border:none;")
        self.confirmButton = QPushButton(self)
        self.confirmButton.setText("Confirm")
        self.confirmButton.setGeometry(60, 90, 160, 32)
        self.confirmButton.clicked.connect(self.OnShow)
        self.confirmButton.setStyleSheet("background:#21ce99; border-radius:15px;color:white; font-size:16px;")

    def OnShow(self):
        self.close()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.offset = event.pos()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.offset is not None and event.buttons() == Qt.LeftButton:
            self.move(self.pos() + event.pos() - self.offset)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.offset = None
        super().mouseReleaseEvent(event)


if __name__ == '__main__':
    import sys

    global app
    app = QApplication(sys.argv)
    MW = MainWindow()
    MW.show()
    sys.exit(app.exec_())
