#!/usr/bin/env python3
import asyncio
import os.path
import sys

os.environ["QUAMASH_QTIMPL"] = "PyQt4"
sys.path.insert(0, os.path.abspath("../asyncio-xmpp"))
sys.path.insert(0, os.path.abspath("../asyncio_xmpp"))

import mlxc.qt.Qt as Qt
import quamash

app = Qt.QApplication(sys.argv)

import mlxc.qt

asyncio.set_event_loop(quamash.QEventLoop(app=app))
loop = asyncio.get_event_loop()
mlxc.qt.spawn_main(loop)
loop.run_forever()
