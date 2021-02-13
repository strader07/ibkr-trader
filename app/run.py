
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QTextEdit, QPushButton, QLineEdit, QPlainTextEdit, \
    QComboBox, QFileDialog, QTableWidget, QTableWidgetItem, QAbstractItemView
from PyQt5.QtCore import QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont, QPainter, QPen, QBrush, QTextCursor
from PyQt5.QtCore import Qt, QObject

import time
import ast
import json
import logging
from datetime import datetime

from ib_insync import *
from engine import Engine

INIT_PRODUCTS = "ESH1, ZNH1, AAPL"
INIT_TIMEFRAME = "15 mins"
INIT_SIZE = "1"
INIT_MAX_CURRENT_HIGH_PRD = "20"
INIT_MIN_CURRENT_LOW_PRD = "20"
INIT_MAX_PAST_HIGH_LAG = "10"
INIT_MAX_PAST_HIGH_PRD = "10"
INIT_MIN_PAST_LOW_LAG = "10"
INIT_MIN_PAST_LOW_PRD = "10"
INIT_PERCENT_CHANGE_LAG = "1"
INIT_SD_LAG = "10"
INIT_NORM_THRESHOLD = "0.7"
INIT_TICK = "1.0"
INIT_STOP_LIMIT_TICKS = "3"
INIT_MAX_PRD_HOLD = "10"
INIT_TARGET_SD = "2"
INIT_STOP_SD = "4"
INIT_MAX_STOP_SD = "6"

INIT_PROD_PARAMS = {
    "ESH1": "tick = 0.25, percent_entry = 0.1",
    "ZNH1": "tick = (1/64)",
    "AAPL": "tick = 0.01, size = 25, max_past_high_lag = 5, min_past_low_lag = 5, bar_size = 60"
}


class MessageBox(QWidget):
    countChanged = pyqtSignal(str)

    def __init__(self, message):
        self.message = message
        super(MessageBox, self).__init__()
        self.setGeometry(850, 600, 320, 222)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.backgroundLabel = QLabel(self)
        self.backgroundLabel.setGeometry(0, 0, 320, 222)
        self.backgroundLabel.setStyleSheet("background-image : url(res/messagebox.png); background-repeat: no-repeat;")

        self.messageContent = QLabel(self)
        self.messageContent.setText(self.message)
        self.messageContent.setGeometry(34, 82, 280, 40)
        self.messageContent.setStyleSheet("color:white; font-size:16px;")
        self.saveButton = QPushButton(self)
        self.saveButton.setText("Ok")
        self.saveButton.setGeometry(120, 144, 100, 40)
        self.saveButton.clicked.connect(self.OnClose)
        self.saveButton.setStyleSheet("background:#21ce99; border-radius:8px;color:white; font-size:18px; ")
        self.closeBtn = QPushButton(self)
        self.closeBtn.setGeometry(295, 5, 20, 20)
        self.closeBtn.setStyleSheet("background-image : url(res/close3.png);background-color: transparent; ")
        self.closeBtn.clicked.connect(self.OnClose)

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


class QTextEditLogger(logging.Handler, QObject):
    appendPlainText = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__()
        QObject.__init__(self)

        self.openDialog = QFileDialog(parent)

        self.widget = QPlainTextEdit(parent)
        self.widget.setReadOnly(True)
        self.widget.setGeometry(740, 460, 280, 460)
        try:
            _date = datetime.now().date()
            f = open(f"loggers/activity-log-{_date}.log", "r")
            logs = f.read()
            f.close()
        except:
            logs = ""
        self.widget.setPlainText(logs)
        self.widget.setStyleSheet(
            "background-color: transparent; border-radius: 1px; color:white; font-size:12px;")
        self.appendPlainText.connect(self.widget.appendPlainText)
        self.widget.moveCursor(QTextCursor.End)
        self.widget.ensureCursorVisible()

        self.clearLogBtn = QPushButton(parent)
        self.clearLogBtn.setGeometry(1000, 425, 20, 20)
        self.clearLogBtn.setStyleSheet(
            "background-image : url(res/delete-mini.png);background-color: transparent;width:25px;height:25px")
        self.clearLogBtn.clicked.connect(self.clear_log)

        self.saveLogBtn = QPushButton(parent)
        self.saveLogBtn.setGeometry(970, 425, 20, 20)
        self.saveLogBtn.setStyleSheet(
            "background-image : url(res/save-mini2.png);background-color: transparent;width:25px;height:25px")
        self.saveLogBtn.clicked.connect(self.save_log)

    def save_log(self):
        path, filter = QFileDialog.getSaveFileName()
        if not path:
            return

        self._save_log_to_path(path)

    def _save_log_to_path(self, path):
        text = self.widget.toPlainText()
        try:
            with open(path, 'w') as f:
                f.write(text)
            logging.getLogger().debug(f"The logs are saved to the file - {path}")

        except Exception as e:
            logging.getLogger().debug(e)

    def clear_log(self):
        _date = datetime.now().date()
        f = open(f"loggers/activity-log-{_date}.log", "w")
        f.write("")
        f.close()

        self.widget.setPlainText("")

    def emit(self, record):
        msg = self.format(record)
        self.appendPlainText.emit(msg)


class MainThread(QThread):
    """
    Runs a counter thread.
    """
    countChanged = pyqtSignal(str)

    def __init__(self, localh_host, port_num, params, parent=None):
        QThread.__init__(self, parent)
        self.localh_host = localh_host
        self.port_num = port_num
        self.params = params
        self.conn_state = False

        try:
            self.ib = IB()
            self.ib.connect(self.localh_host, self.port_num, clientId=23)
            self.conn_state = True
            logging.getLogger().debug("Successfully connected!")
        except Exception as e:
            logging.getLogger().debug(e)
            self.ib.disconnect()
            self.terminate()

    def run(self):
        state_msg = {"connection": self.conn_state}
        self.countChanged.emit(str(state_msg))
        engine = Engine(params=self.params)
        while self.conn_state:
            try:
                engine.start()
                print("Engine started")
                time.sleep(5)
            except Exception as e:
                print(e)
            time.sleep(1)

    def stop(self):
        self.ib.disconnect()
        self.conn_state = False
        print("Disconnected")
        logging.getLogger().debug("Successfully disconnected!")
        self.terminate()


class MainWindow(QWidget):

    def __init__(self):
        super(MainWindow, self).__init__()
        self.setGeometry(250, 30, 1200, 1080)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Interactive Brokers Trader")
        self.start_flag = 1

        try:
            with open("settings/generalParams.json", "r") as f:
                data = json.load(f)
        except Exception as e:
            print(e)
            data = {}
        try:
            with open("settings/productSpecificParams.json", "r") as f:
                prod_params = json.load(f)
        except Exception as e:
            print(e)
            prod_params = {}

        if prod_params:
            self.prod_params = prod_params
        else:
            self.prod_params = INIT_PROD_PARAMS

        if data:
            self.params = data
        else:
            self.params = {
                "products": INIT_PRODUCTS,
                "timeframe": INIT_TIMEFRAME,
                "size": INIT_SIZE,
                "max_current_high_prd": INIT_MAX_CURRENT_HIGH_PRD,
                "max_past_high_lag": INIT_MAX_PAST_HIGH_LAG,
                "max_past_high_prd": INIT_MAX_PAST_HIGH_PRD,
                "min_current_low_prd": INIT_MIN_CURRENT_LOW_PRD,
                "min_past_low_lag": INIT_MIN_PAST_LOW_LAG,
                "min_past_low_prd": INIT_MIN_PAST_LOW_PRD,
                "percent_change_lag": INIT_PERCENT_CHANGE_LAG,
                "sd_lag": INIT_SD_LAG,
                "tick": INIT_TICK,
                "stop_limit_ticks": INIT_STOP_LIMIT_TICKS,
                "norm_threshold": INIT_NORM_THRESHOLD,
                "max_prd_hold": INIT_MAX_PRD_HOLD,
                "target_sd": INIT_TARGET_SD,
                "stop_sd": INIT_STOP_SD,
                "max_stop_sd": INIT_MAX_STOP_SD
            }

        self.backgroundLabel = QLabel(self)
        self.backgroundLabel.setGeometry(0, 0, 1200, 1080)
        self.backgroundLabel.setStyleSheet("background-image : url(res/main_ui.png); background-repeat: no-repeat;")
        font = QFont()
        font.setPointSize(20)
        self.closeBtn = QPushButton(self)
        self.closeBtn.setGeometry(1040, 30, 30, 30)
        self.closeBtn.setStyleSheet("background-image : url(res/close2.png);background-color: transparent;")
        self.closeBtn.clicked.connect(self.onClose)

        self.optionBtn = QPushButton(self)
        self.optionBtn.setGeometry(980, 25, 41, 41)
        self.optionBtn.setStyleSheet("background-image : url(res/option.png);background-color: transparent;")
        self.optionBtn.clicked.connect(self.OpenSetting)

        self.startBtn = QPushButton(self)
        self.startBtn.setGeometry(760, 280, 300, 48)
        self.startBtn.setText("Start")
        self.startBtn.setStyleSheet("background-color: #db1222; border-radius: 16px; color:white; font-size:20px;")
        self.startBtn.clicked.connect(self.onStart)

        self.productSetParamTxt = QLabel(self)
        self.productSetParamTxt.setStyleSheet(
            "background-color: transparent; border-radius: 15px; color:white; font-size:18px;")
        self.productSetParamTxt.setGeometry(80, 150, 400, 36)
        self.productSetParamTxt.setText("- Products Specific Setup -")

        # self.productSetParamEdit = QTextEdit(self)
        # self.productSetParamEdit.setStyleSheet(
        #     "background-color: transparent; border-radius: 1px; color:white; font-size:14px;")
        # self.productSetParamEdit.setGeometry(80, 205, 590, 100)
        # self.productSetParamEdit.moveCursor(QTextCursor.End)
        # self.productSetParamEdit.ensureCursorVisible()
        # self.productSetParamEdit.insertPlainText(self.prod_params)
        # self.productSetParamEdit.setReadOnly(True)

        self.tableWidget = QTableWidget(self)
        self.tableWidget.setGeometry(82, 210, 590, 100)
        self.tableWidget.resizeColumnsToContents()
        self.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tableWidget.setStyleSheet(
            "selection-background-color: transparent; background-color: transparent; border-radius: 1px; color:white; font-size:14px;")
        self.tableWidget.horizontalHeader().hide()
        self.tableWidget.verticalHeader().hide()
        products = [prod.strip(",. ") for prod in self.params["products"].split(",")]
        self.tableWidget.setRowCount(len(products))
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setColumnWidth(0, 100)
        self.tableWidget.setColumnWidth(1, 460)
        for i in range(len(products)):
            self.tableWidget.setItem(i, 0, QTableWidgetItem(products[i]))
            if products[i] in self.prod_params:
                self.tableWidget.setItem(i, 1, QTableWidgetItem(self.prod_params[products[i]]))
            else:
                self.tableWidget.setItem(i, 1, QTableWidgetItem(""))
        self.tableWidget.doubleClicked.connect(self.on_click)

        self.editBtn = QPushButton(self)
        self.editBtn.setGeometry(495, 154, 80, 32)
        self.editBtn.setText("Edit")
        self.editBtn.setStyleSheet("background-color: #db1222; border-radius: 12px; color:white; font-size:18px;")
        self.editBtn.clicked.connect(self.onEditProductsParam)
        self.saveBtn = QPushButton(self)
        self.saveBtn.setGeometry(590, 154, 80, 32)
        self.saveBtn.setText("Save")
        self.saveBtn.setStyleSheet("background-color: #db1222; border-radius: 12px; color:white; font-size:18px;")
        self.saveBtn.clicked.connect(self.onSaveProductsParam)

        self.localhost = QLineEdit(self)
        self.localhost.setStyleSheet("background-color: transparent; border-radius: 15px; color:white; font-size:20px;")
        self.localhost.setGeometry(900, 150, 180, 24)
        self.localhost.setText("127.0.0.1")
        self.port = QLineEdit(self)
        self.port.setStyleSheet("background-color: transparent; border-radius: 15px; color:white; font-size:20px;")
        self.port.setGeometry(900, 220, 150, 24)
        self.port.setText("7497")

        self.logTextBox = QTextEditLogger(self)
        self.logTextBox.setFormatter(
            logging.Formatter(
                '\n=== %(asctime)s %(module)s ===\n\n%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p'))
        logging.getLogger().addHandler(self.logTextBox)
        logging.getLogger().setLevel(logging.DEBUG)

        # log to file
        _date = datetime.now().date()
        fh = logging.FileHandler(f'loggers/activity-log-{_date}.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter(
                '\n=== %(asctime)s %(module)s ===\n\n%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p'))
        logging.getLogger().addHandler(fh)

    @pyqtSlot()
    def on_click(self):
        for currentQTableWidgetItem in self.tableWidget.selectedItems():
            print(currentQTableWidgetItem.row(), currentQTableWidgetItem.column(), currentQTableWidgetItem.text())

    def onEditProductsParam(self):
        # self.productSetParamEdit.setReadOnly(False)
        # self.productSetParamEdit.moveCursor(QTextCursor.End)
        # self.productSetParamEdit.ensureCursorVisible()
        # self.productSetParamEdit.setFocus()
        self.tableWidget.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.tableWidget.setFocus()
        self.tableWidget.setCurrentCell(0, 1)

    def onSaveProductsParam(self):
        products = [prod.strip(",. ") for prod in self.params["products"].split(",")]
        prod_params = {}
        for i in range(len(products)):
            prod_params[products[i]] = self.tableWidget.item(i, 1).text()
        self.prod_params = prod_params
        try:
            with open("settings/productSpecificParams.json", "w") as f:
                json.dump(prod_params, f)
        except Exception as e:
            print(e)
        self.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        print(self.prod_params)
        log = logging.getLogger()
        log.debug(self.prod_params)

    def onStart(self):
        if self.start_flag == 1:
            if self.localhost.text() != '' and self.port.text() != '':
                try:
                    self.main_thread = MainThread(localh_host=self.localhost.text(), port_num=int(self.port.text()),
                                                  params=self.params)
                    self.main_thread.countChanged.connect(self.onProcess)
                    self.main_thread.start()
                    # self.start_flag = 0
                    # self.startBtn.setText("Stop")
                except Exception as e:
                    self.msg = MessageBox(e)
                    self.msg.show()
            else:
                try:
                    if self.localhost.text() == '':
                        self.msg = MessageBox("Please enter your host url!")
                        self.msg.show()
                    else:
                        self.msg = MessageBox("Please enter your port number!")
                        self.msg.show()
                except Exception as e:
                    print(e)
        else:
            self.startBtn.setText("Start")
            self.start_flag = 1
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
        msg = ast.literal_eval(value)
        if not msg["connection"]:
            self.main_thread.stop()
            self.start_flag = 1
            self.msg = MessageBox("Connection failed!!!")
            self.msg.show()
        else:
            self.start_flag = 0
            self.startBtn.setText("Stop")

        # self.listwidget.addItem(value)

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

    def SettingsUpdate(self, param_string):
        params = ast.literal_eval(param_string)
        self.params = params

        print(params)
        self.updateProductsParamTable()

    def updateProductsParamTable(self):
        self.tableWidget.setRowCount(0)
        products = [prod.strip(",. ") for prod in self.params["products"].split(",")]
        self.tableWidget.setRowCount(len(products))
        for i in range(len(products)):
            self.tableWidget.setItem(i, 0, QTableWidgetItem(products[i]))
            if products[i] in self.prod_params:
                self.tableWidget.setItem(i, 1, QTableWidgetItem(self.prod_params[products[i]]))
            else:
                self.tableWidget.setItem(i, 1, QTableWidgetItem(""))

    def OpenSetting(self):
        try:
            self.SW = SettingsWindow(self.params, self.start_flag)
            self.SW.countChanged.connect(self.SettingsUpdate)
            self.SW.show()
        except Exception as e:
            print(e)


class SettingsWindow(QWidget):
    countChanged = pyqtSignal(str)

    def __init__(self, params, start_flag):

        self.params = params
        self.start_flag = start_flag

        super(SettingsWindow, self).__init__()

        self.setFixedSize(900, 1000)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background:#0b0b0b;")
        setting_icon = QPushButton(self)
        setting_icon.setGeometry(20, 30, 40, 40)
        setting_icon.setStyleSheet("background-image : url(res/option.png);background-color: transparent; ")
        self.titleText = QLabel(self)
        self.titleText.setText("Parameters Module")
        self.titleText.setGeometry(80, 10, 300, 80)
        self.titleText.setStyleSheet("color:white; font-size:28px;border:none; font-family: Arial, Helvetica, "
                                     "sans-serif;")

        self.productsLabel = QLabel(self)
        self.productsLabel.setGeometry(40, 150, 200, 40)
        self.productsLabel.setText("Products:")
        self.productsLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.productsEdit = QLineEdit(self)
        self.productsEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;padding-left:5px;")
        self.productsEdit.setGeometry(250, 150, 600, 40)
        self.productsEdit.setAlignment(Qt.AlignLeft)
        self.productsEdit.setText(self.params["products"])
        self.productsEdit.setReadOnly(True)

        self.timeframeLabel = QLabel(self)
        self.timeframeLabel.setGeometry(40, 210, 150, 40)
        self.timeframeLabel.setText("Time Frame:")
        self.timeframeLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.timeframe_combo = QComboBox(self)
        self.time_frame_list = ['30 secs', '1 min', '2 mins', '3 mins', '5 mins', '10 mins', '15 mins', '20 mins', '30 mins', '1 hour', '2 hours', '3 hours', '4 hours', '8 hours', '1 day', '1 week', '1 month']
        for item1 in self.time_frame_list:
            self.timeframe_combo.addItem(item1)
        idx = self.time_frame_list.index(self.params["timeframe"])
        self.timeframe_combo.setCurrentIndex(idx)
        self.timeframe_combo.setStyleSheet("background-color:#24202a;color:white;font-size:16px;border:none;padding-left:5px;")
        self.timeframe_combo.setGeometry(250, 210, 150, 40)
        # self.timeframe_combo.setReadOnly(True)

        self.sizeLabel = QLabel(self)
        self.sizeLabel.setGeometry(490, 210, 200, 40)
        self.sizeLabel.setText("Trade Size:")
        self.sizeLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.sizeEdit = QLineEdit(self)
        self.sizeEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.sizeEdit.setGeometry(700, 210, 150, 40)
        self.sizeEdit.setAlignment(Qt.AlignCenter)
        self.sizeEdit.setText(self.params["size"])
        self.sizeEdit.setReadOnly(True)

        self.maxCurrentHighPeriodsLabel = QLabel(self)
        self.maxCurrentHighPeriodsLabel.setGeometry(40, 290, 200, 40)
        self.maxCurrentHighPeriodsLabel.setText("Max Current High Periods:")
        self.maxCurrentHighPeriodsLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.maxCurrentHighPeriodsEdit = QLineEdit(self)
        self.maxCurrentHighPeriodsEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.maxCurrentHighPeriodsEdit.setGeometry(250, 290, 150, 40)
        self.maxCurrentHighPeriodsEdit.setAlignment(Qt.AlignCenter)
        self.maxCurrentHighPeriodsEdit.setText(self.params["max_current_high_prd"])
        self.maxCurrentHighPeriodsEdit.setReadOnly(True)

        self.maxPastHighLagLabel = QLabel(self)
        self.maxPastHighLagLabel.setGeometry(40, 350, 200, 40)
        self.maxPastHighLagLabel.setText("Max Past High Lag:")
        self.maxPastHighLagLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.maxPastHighLagEdit = QLineEdit(self)
        self.maxPastHighLagEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.maxPastHighLagEdit.setGeometry(250, 350, 150, 40)
        self.maxPastHighLagEdit.setAlignment(Qt.AlignCenter)
        self.maxPastHighLagEdit.setText(self.params["max_past_high_lag"])
        self.maxPastHighLagEdit.setReadOnly(True)

        self.maxPastHighPeriodsLabel = QLabel(self)
        self.maxPastHighPeriodsLabel.setGeometry(40, 410, 200, 40)
        self.maxPastHighPeriodsLabel.setText("Max Past High Periods:")
        self.maxPastHighPeriodsLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.maxPastHighPeriodsEdit = QLineEdit(self)
        self.maxPastHighPeriodsEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.maxPastHighPeriodsEdit.setGeometry(250, 410, 150, 40)
        self.maxPastHighPeriodsEdit.setAlignment(Qt.AlignCenter)
        self.maxPastHighPeriodsEdit.setText(self.params["max_past_high_prd"])
        self.maxPastHighPeriodsEdit.setReadOnly(True)

        self.minCurrentLowPeriodsLabel = QLabel(self)
        self.minCurrentLowPeriodsLabel.setGeometry(490, 290, 200, 40)
        self.minCurrentLowPeriodsLabel.setText("Min Current Low Periods:")
        self.minCurrentLowPeriodsLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.minCurrentLowPeriodsEdit = QLineEdit(self)
        self.minCurrentLowPeriodsEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.minCurrentLowPeriodsEdit.setGeometry(700, 290, 150, 40)
        self.minCurrentLowPeriodsEdit.setAlignment(Qt.AlignCenter)
        self.minCurrentLowPeriodsEdit.setText(self.params["min_current_low_prd"])
        self.minCurrentLowPeriodsEdit.setReadOnly(True)

        self.minPastLowLagLabel = QLabel(self)
        self.minPastLowLagLabel.setGeometry(490, 350, 200, 40)
        self.minPastLowLagLabel.setText("Min Past Low Lag:")
        self.minPastLowLagLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.minPastLowLagEdit = QLineEdit(self)
        self.minPastLowLagEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.minPastLowLagEdit.setGeometry(700, 350, 150, 40)
        self.minPastLowLagEdit.setAlignment(Qt.AlignCenter)
        self.minPastLowLagEdit.setText(self.params["min_past_low_lag"])
        self.minPastLowLagEdit.setReadOnly(True)

        self.minPastLowPeriodsLabel = QLabel(self)
        self.minPastLowPeriodsLabel.setGeometry(490, 410, 200, 40)
        self.minPastLowPeriodsLabel.setText("Min Past Low Periods:")
        self.minPastLowPeriodsLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.minPastLowPeriodsEdit = QLineEdit(self)
        self.minPastLowPeriodsEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.minPastLowPeriodsEdit.setGeometry(700, 410, 150, 40)
        self.minPastLowPeriodsEdit.setAlignment(Qt.AlignCenter)
        self.minPastLowPeriodsEdit.setText(self.params["min_past_low_prd"])
        self.minPastLowPeriodsEdit.setReadOnly(True)

        self.percentChangeLagLabel = QLabel(self)
        self.percentChangeLagLabel.setGeometry(40, 490, 200, 40)
        self.percentChangeLagLabel.setText("Percent Change Lag:")
        self.percentChangeLagLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.percentChangeLagEdit = QLineEdit(self)
        self.percentChangeLagEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.percentChangeLagEdit.setGeometry(250, 490, 150, 40)
        self.percentChangeLagEdit.setAlignment(Qt.AlignCenter)
        self.percentChangeLagEdit.setText(self.params["percent_change_lag"])
        self.percentChangeLagEdit.setReadOnly(True)

        self.sdLagLabel = QLabel(self)
        self.sdLagLabel.setGeometry(490, 490, 200, 40)
        self.sdLagLabel.setText("Sd Lag:")
        self.sdLagLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.sdLagEdit = QLineEdit(self)
        self.sdLagEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.sdLagEdit.setGeometry(700, 490, 150, 40)
        self.sdLagEdit.setAlignment(Qt.AlignCenter)
        self.sdLagEdit.setText(self.params["sd_lag"])
        self.sdLagEdit.setReadOnly(True)

        self.tickLabel = QLabel(self)
        self.tickLabel.setGeometry(40, 570, 200, 40)
        self.tickLabel.setText("Tick:")
        self.tickLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.tickEdit = QLineEdit(self)
        self.tickEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.tickEdit.setGeometry(250, 570, 150, 40)
        self.tickEdit.setAlignment(Qt.AlignCenter)
        self.tickEdit.setText(self.params["tick"])
        self.tickEdit.setReadOnly(True)

        self.stopLimitTicksLabel = QLabel(self)
        self.stopLimitTicksLabel.setGeometry(40, 630, 200, 40)
        self.stopLimitTicksLabel.setText("Stop Limit Ticks:")
        self.stopLimitTicksLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.stopLimitTicksEdit = QLineEdit(self)
        self.stopLimitTicksEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.stopLimitTicksEdit.setGeometry(250, 630, 150, 40)
        self.stopLimitTicksEdit.setAlignment(Qt.AlignCenter)
        self.stopLimitTicksEdit.setText(self.params["stop_limit_ticks"])
        self.stopLimitTicksEdit.setReadOnly(True)

        self.normThresholdLabel = QLabel(self)
        self.normThresholdLabel.setGeometry(490, 570, 200, 40)
        self.normThresholdLabel.setText("Norm Threshold:")
        self.normThresholdLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.normThresholdEdit = QLineEdit(self)
        self.normThresholdEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.normThresholdEdit.setGeometry(700, 570, 150, 40)
        self.normThresholdEdit.setAlignment(Qt.AlignCenter)
        self.normThresholdEdit.setText(self.params["norm_threshold"])
        self.normThresholdEdit.setReadOnly(True)

        self.maxPeriodHoldLabel = QLabel(self)
        self.maxPeriodHoldLabel.setGeometry(490, 630, 200, 40)
        self.maxPeriodHoldLabel.setText("Max Period Hold:")
        self.maxPeriodHoldLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.maxPeriodHoldEdit = QLineEdit(self)
        self.maxPeriodHoldEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.maxPeriodHoldEdit.setGeometry(700, 630, 150, 40)
        self.maxPeriodHoldEdit.setAlignment(Qt.AlignCenter)
        self.maxPeriodHoldEdit.setText(self.params["max_prd_hold"])
        self.maxPeriodHoldEdit.setReadOnly(True)

        self.targetSdLabel = QLabel(self)
        self.targetSdLabel.setGeometry(40, 710, 200, 40)
        self.targetSdLabel.setText("Target Sd:")
        self.targetSdLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.targetSdEdit = QLineEdit(self)
        self.targetSdEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.targetSdEdit.setGeometry(250, 710, 150, 40)
        self.targetSdEdit.setAlignment(Qt.AlignCenter)
        self.targetSdEdit.setText(self.params["target_sd"])
        self.targetSdEdit.setReadOnly(True)

        self.stopSdLabel = QLabel(self)
        self.stopSdLabel.setGeometry(490, 710, 200, 40)
        self.stopSdLabel.setText("Stop Sd:")
        self.stopSdLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.stopSdEdit = QLineEdit(self)
        self.stopSdEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.stopSdEdit.setGeometry(700, 710, 150, 40)
        self.stopSdEdit.setAlignment(Qt.AlignCenter)
        self.stopSdEdit.setText(self.params["stop_sd"])
        self.stopSdEdit.setReadOnly(True)

        self.maxStopSdLabel = QLabel(self)
        self.maxStopSdLabel.setGeometry(40, 770, 200, 40)
        self.maxStopSdLabel.setText("Max Stop Sd:")
        self.maxStopSdLabel.setStyleSheet("color:white; font-size:16px;border:none;")
        self.maxStopSdEdit = QLineEdit(self)
        self.maxStopSdEdit.setStyleSheet("background:#24202a; color:white; font-size:16px;border:none;")
        self.maxStopSdEdit.setGeometry(250, 770, 150, 40)
        self.maxStopSdEdit.setAlignment(Qt.AlignCenter)
        self.maxStopSdEdit.setText(self.params["max_stop_sd"])
        self.maxStopSdEdit.setReadOnly(True)

        self.editButton = QPushButton(self)
        self.editButton.setText("Edit")
        self.editButton.setGeometry(500, 910, 150, 40)
        self.editButton.clicked.connect(self.OnEditClick)
        self.editButton.setStyleSheet("background:#db1222; border-radius:8px;color:white; font-size:16px;")

        self.confirmButton = QPushButton(self)
        self.confirmButton.setText("Save")
        self.confirmButton.setGeometry(700, 910, 150, 40)
        self.confirmButton.clicked.connect(self.OnShow)
        self.confirmButton.setStyleSheet("background:#db1222; border-radius:8px;color:white; font-size:16px;")

        self.closeBtn = QPushButton(self)
        self.closeBtn.setGeometry(865, 5, 30, 30)
        self.closeBtn.setStyleSheet("background-image : url(res/close2.png);background-color: transparent; ")
        self.closeBtn.clicked.connect(self.OnClose)

    def OnEditClick(self):
        if self.start_flag == 0:
            self.msg = MessageBox("You can't edit when bot is running!")
            self.msg.show()
            read_only = True
        else:
            read_only = False
        self.productsEdit.setReadOnly(read_only)
        self.productsEdit.setFocus()
        # self.timeframe_combo.setReadOnly(read_only)
        self.sizeEdit.setReadOnly(read_only)
        self.maxCurrentHighPeriodsEdit.setReadOnly(read_only)
        self.maxPastHighLagEdit.setReadOnly(read_only)
        self.maxPastHighPeriodsEdit.setReadOnly(read_only)
        self.minCurrentLowPeriodsEdit.setReadOnly(read_only)
        self.minPastLowLagEdit.setReadOnly(read_only)
        self.minPastLowPeriodsEdit.setReadOnly(read_only)
        self.percentChangeLagEdit.setReadOnly(read_only)
        self.sdLagEdit.setReadOnly(read_only)
        self.tickEdit.setReadOnly(read_only)
        self.stopLimitTicksEdit.setReadOnly(read_only)
        self.normThresholdEdit.setReadOnly(read_only)
        self.maxPeriodHoldEdit.setReadOnly(read_only)
        self.targetSdEdit.setReadOnly(read_only)
        self.stopSdEdit.setReadOnly(read_only)
        self.maxStopSdEdit.setReadOnly(read_only)

    def OnShow(self):
        timeframe = self.time_frame_list[self.timeframe_combo.currentIndex()]
        params = {
            "products": self.productsEdit.text(),
            "timeframe": str(timeframe),
            "size": self.sizeEdit.text(),
            "max_current_high_prd": self.maxCurrentHighPeriodsEdit.text(),
            "max_past_high_lag": self.maxPastHighLagEdit.text(),
            "max_past_high_prd": self.maxPastHighPeriodsEdit.text(),
            "min_current_low_prd": self.minCurrentLowPeriodsEdit.text(),
            "min_past_low_lag": self.minPastLowLagEdit.text(),
            "min_past_low_prd": self.minPastLowPeriodsEdit.text(),
            "percent_change_lag": self.percentChangeLagEdit.text(),
            "sd_lag": self.sdLagEdit.text(),
            "tick": self.tickEdit.text(),
            "stop_limit_ticks": self.stopLimitTicksEdit.text(),
            "norm_threshold": self.normThresholdEdit.text(),
            "max_prd_hold": self.maxPeriodHoldEdit.text(),
            "target_sd": self.targetSdEdit.text(),
            "stop_sd": self.stopSdEdit.text(),
            "max_stop_sd": self.maxStopSdEdit.text()
        }
        try:
            with open("settings/generalParams.json", "w") as f:
                json.dump(params, f)
                logging.getLogger().debug(f"New parameters:\n{params}\nFile path:\n{f.name}\n")
        except Exception as e:
            print(e)
            logging.getLogger().debug(f"Save parameters error:\n{e}\n")
        param_string = str(params)
        self.countChanged.emit(param_string)

        self.productsEdit.setReadOnly(True)
        # self.timeframe_combo.setReadOnly(True)
        self.sizeEdit.setReadOnly(True)
        self.maxCurrentHighPeriodsEdit.setReadOnly(True)
        self.maxPastHighLagEdit.setReadOnly(True)
        self.maxPastHighPeriodsEdit.setReadOnly(True)
        self.minCurrentLowPeriodsEdit.setReadOnly(True)
        self.minPastLowLagEdit.setReadOnly(True)
        self.minPastLowPeriodsEdit.setReadOnly(True)
        self.percentChangeLagEdit.setReadOnly(True)
        self.sdLagEdit.setReadOnly(True)
        self.tickEdit.setReadOnly(True)
        self.stopLimitTicksEdit.setReadOnly(True)
        self.normThresholdEdit.setReadOnly(True)
        self.maxPeriodHoldEdit.setReadOnly(True)
        self.targetSdEdit.setReadOnly(True)
        self.stopSdEdit.setReadOnly(True)
        self.maxStopSdEdit.setReadOnly(True)
        self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.lightGray)
        painter.drawLine(0, 100, 900, 100)
        painter.drawLine(0, 860, 900, 860)

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


if __name__ == '__main__':
    import sys

    global app
    app = QApplication(sys.argv)
    MW = MainWindow()
    MW.show()
    sys.exit(app.exec_())
