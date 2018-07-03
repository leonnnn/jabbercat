from .. import Qt


class MemberCompleter(Qt.QCompleter):
    def eventFilter(self, o, e):
        if e.type() == Qt.QEvent.KeyPress:
            print(o is self.widget(),
                  o is self.popup(),
                  e.type() == Qt.QEvent.KeyPress,
                  e.isAccepted(),
                  self.currentIndex().isValid())
        return super().eventFilter(o, e)

    def complete(self, rect: Qt.QRect = Qt.QRect()):
        super().complete(rect)
        if self.popup().isVisible():
            print("complete", "is visible")
            if self.currentIndex().isValid():
                self.popup().setCurrentIndex(self.currentIndex())
                self.popup().selectionModel().select(
                    self.currentIndex(),
                    Qt.QItemSelectionModel.Select
                )


class MessageInput(Qt.QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(False)
        self._completer = None
        self._completion_inhibited = False

    @Qt.pyqtProperty(Qt.QCompleter)
    def completer(self):
        return self._completer

    def _completer_activated(self, arg):
        print("_completer_activated", arg)
        completion_cursor = self._completion_cursor()
        completion_cursor.deleteChar()
        completion_cursor.insertText(arg)
        completion_cursor.insertText(", ")

    def _completion_cursor(self):
        word_cursor = self.textCursor()
        # FIXME: this doesn’t work well with all types of nicknames...
        word_cursor.select(Qt.QTextCursor.WordUnderCursor)
        return word_cursor

    @completer.setter
    def completer(self, new):
        if self._completer is not None:
            self._completer.setWidget(None)
            self._completer.activated.disconnect(self._completer_activated)
        self._completer = new
        if self._completer is not None:
            self._completer.setWidget(self)
            self._completer.setCompletionMode(Qt.QCompleter.PopupCompletion)
            self._completer.setCaseSensitivity(Qt.Qt.CaseInsensitive)
            self._completer.activated.connect(self._completer_activated)

    def mousePressEvent(self, event: Qt.QMouseEvent):
        self._completion_inhibited = False
        return super().mousePressEvent(event)

    def keyPressEvent(self, event: Qt.QKeyEvent):
        if (self._completer and self._completer.popup() and
                self._completer.popup().isVisible()):
            if event.key() in (Qt.Qt.Key_Enter, Qt.Qt.Key_Tab,
                               Qt.Qt.Key_Backtab,
                               Qt.Qt.Key_Return):
                event.ignore()
                return
            if event.key() == Qt.Qt.Key_Escape:
                self._completion_inhibited = True
                self._completer.popup().hide()
                event.ignore()
                return

        if event.key() in (Qt.Qt.Key_Space,
                           Qt.Qt.Key_Left,
                           Qt.Qt.Key_Right,
                           Qt.Qt.Key_Up,
                           Qt.Qt.Key_Down,
                           Qt.Qt.Key_Return,
                           Qt.Qt.Key_Enter):
            self._completion_inhibited = False

        super().keyPressEvent(event)
        if self._completer and not self._completion_inhibited:
            completion_cursor = self._completion_cursor()
            text = completion_cursor.selectedText()
            if not text:
                return
            self._completer.setCompletionPrefix(text)
            popup = self._completer.popup()
            cr = self.cursorRect(completion_cursor)
            cr.setWidth(
                self.completer.popup().sizeHintForColumn(0) +
                self.completer.popup().verticalScrollBar().sizeHint().width()
            )
            self._completer.complete(cr)
