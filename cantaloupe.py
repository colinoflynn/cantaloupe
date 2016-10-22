#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2016 Colin O'Flynn
#
# This file is released under The MIT License (MIT)
#
import logging
import sys
import platform
import glob
import serial

from cantact import CantactDev

try:
    from PySide.QtCore import *
    from PySide.QtGui import *
except ImportError, e:
    print "**********************************************"
    print "ERROR: PySide is required for this program.\nTry installing with 'pip install pyside' first."
    print "**********************************************\n\n"

    print "Failed to import 'PySide', original exception information:"
    raise

try:
    import pyqtgraph
    pyqtgraph.setConfigOption('background', 'w')
    pyqtgraph.setConfigOption('foreground', 'k')
except ImportError, e:
    print "***********************************************"
    print "ERROR: PyQtGraph is required for this program.\nTry installing with 'pip install pyqtgraph' first."
    print "***********************************************\n\n"

    print "Failed to import 'pyqtgraph', full exception trace given below in case it's another problem:"
    raise


def scan():
    """scan for available ports. return a list of names"""
    system_name = platform.system()
    if system_name == 'Windows':
      available = []
      for i in range(200):
          try:
              s = serial.Serial(i)
              available.append(s.portstr)
              s.close()   # explicit close 'cause of delayed GC in java
          except serial.SerialException:
              pass
      return available
    else:
      return glob.glob('/dev/ttyS*') + glob.glob('/dev/ttyUSB*')

__author__ = "Colin O'Flynn"


class CANtaloupeGUI(QMainWindow):
    def __init__(self):
        super(CANtaloupeGUI, self).__init__()
        self.timer = QTimer()
        #TODO - is this polling interval enough?
        self.timer.setInterval(1)
        self.timer.timeout.connect(self.checkdata)
        self.timer.stop()
        self.initUI()
        self.hw = None

        self.setWindowTitle("CANtaloupe - Another Craptuclar CAN Thingy")
        self.restoreGeometry(QSettings().value("geometry"))
        self.restoreState(QSettings().value("windowState"))

        self._dlclist = []

    def refreshComs(self, _=None):
        for i in range(0, self.snlist.count()):
            self.snlist.removeItem(i)
        self.snlist.addItems(scan())

    def setupSerialGUI(self):

        self._serialguiwidget =  QWidget()
        layout = QVBoxLayout()
        self.snlist = QComboBox()
        comlayout = QHBoxLayout()
        refreshpb = QPushButton("refresh")
        refreshpb.clicked.connect(self.refreshComs)
        comlayout.addWidget(self.snlist)
        comlayout.addWidget(refreshpb)
        comlayout.addStretch()
        self.snlist.addItems(scan())
        layout.addLayout(comlayout)
        self._serialguiwidget.setLayout(layout)

        self._baudbox = QComboBox()
        self._baudbox.addItems(["%d bps"%b for b in CantactDev.bitrates.keys()])
        self._baudbox.setCurrentIndex(QSettings().value("default-baud", 6))
        layout.addWidget(self._baudbox)

        self.connectbn = QPushButton("Connect!!!")
        self.connectbn.setCheckable(True)
        self.connectbn.clicked.connect(self._connectbnpushed)

        layout.addWidget(self.connectbn)
        layout.addStretch()

        return self._serialguiwidget

    def _connectbnpushed(self, _=None):
        if self.connectbn.isChecked():
            self._con()
            self._baudbox.setEnabled(False)
            self.connectbn.setText("Disconnect!!!")
            QSettings().setValue("default-baud", self._baudbox.currentIndex())
        else:
            self.connectbn.setText("Connect!!!")
            self._dis()
            self._baudbox.setEnabled(True)


    def _con(self):
        self.hw = CantactDev(self.snlist.currentText())
        self.hw.set_bitrate(500000)
        self.hw.start()
        self.timer.start()

    def setupLoggingGUI(self):
        wid = QTableWidget()
        wid.setColumnCount(3+8)
        wid.setHorizontalHeaderLabels(["CAN-ID", "DLC", "D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "Repeat"])
        wid.resizeColumnsToContents()
        self._tablewidget = wid

        layout = QVBoxLayout()
        layoutpbs = QHBoxLayout()

        pbClear = QPushButton("Clear Colours")
        pbClear.clicked.connect(self.clear_colours)
        self.pbMarkNew = QPushButton("New Changes in Green")
        self.pbMarkNew.setCheckable(True)

        layoutpbs.addWidget(pbClear)
        layoutpbs.addWidget(self.pbMarkNew)
        layoutpbs.addStretch()

        layout.addWidget(wid)
        layout.addLayout(layoutpbs)

        mainwid = QWidget()
        mainwid.setLayout(layout)

        return mainwid

    def clear_colours(self):
        for row in range(0, self._tablewidget.rowCount()):
            for i in range(0, 8):
                cell = self._tablewidget.item(row, i+2)
                if cell is not None:
                    cell.setForeground(QBrush(Qt.black))

    def checkdata(self):
        if self.hw.data_available():
            data = self.hw.recv()

            found = -1
            for i,d in enumerate(self._dlclist):
                if d.id == data.id:
                    found = i
                    break

            difflist = [False]*8
            data_changed = False
            dlc_changed = False
            if found < 0:
                self._dlclist.append(data)
                found = len(self._dlclist)
                self._tablewidget.setRowCount(found)
                found -= 1

                #New row - add table items now
                for i in range(0, data.dlc):
                    self._tablewidget.setItem(found, i + 2, QTableWidgetItem("%02X" % data.data[i]))
                self._tablewidget.setItem(found, 0, QTableWidgetItem("%03X" % data.id))
                self._tablewidget.setItem(found, 1, QTableWidgetItem("%d" % data.dlc))

            else:
                #old data, find bytes in differ
                if self._dlclist[found].dlc != data.dlc:
                    #length changed?
                    dlc_changed = True

                for i,d in enumerate(self._dlclist[found].data):
                    if d != data.data[i]:
                        difflist[i] = True
                        data_changed = True

            colour_changed = QBrush(Qt.red)
            colour_newchanged = QBrush(Qt.green)

            #slower - add colour / change diff bytes only
            if data_changed or dlc_changed:
                if dlc_changed:
                    self._tablewidget.item(found, 1).setText("%d"%data.dlc)
                    #DLC changed - clear old data so we don't leave it by accident
                    for i in range(0, 8):
                        self._tablewidget.item(found, i+2).setText("  ")

                for i in range(0, data.dlc):
                    if difflist[i]:
                        cell = self._tablewidget.item(found, i+2)
                        cell.setText("%02X" % data.data[i])

                        if cell.foreground() != colour_changed:
                            #Set colour as requested too
                            if self.pbMarkNew.isChecked():
                                cell.setForeground(colour_newchanged)
                            else:
                                cell.setForeground(colour_changed)

            #Update count
            try:
                cell = self._tablewidget.item(found, 10)
                cnt = int(cell.text())
                cell.setText("%d" % (cnt + 1))
            except:
                self._tablewidget.setItem(found, 10, QTableWidgetItem("1"))


            self._dlclist[found] = data


    def initUI(self):
        tabby = QTabWidget()
        self.setCentralWidget(tabby)

        tabby.addTab(self.setupSerialGUI(), "Serial Setup")
        tabby.addTab(self.setupLoggingGUI(), "Logging Example")

        exitAction = QAction('Exit', self)
        exitAction.setShortcut('Ctrl+Q')
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.close)

        self.statusBar()

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        fileMenu.addAction(exitAction)

        toolbar = self.addToolBar('Exit')
        toolbar.addAction(exitAction)

        self.setGeometry(300, 300, 350, 250)
        self.setWindowTitle('Main window')
        self.show()

    def _dis(self):
        if self.hw:
            self.hw.stop()
            self.hw.ser.close()
            self.hw = None
        self.timer.stop()

    def closeEvent(self, event):
        self._dis()
        QSettings().setValue("geometry", self.saveGeometry())
        QSettings().setValue("windowState", self.saveState())
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("cantaloupe")
    app.setOrganizationName("SomeDude INC")
    ex = CANtaloupeGUI()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()