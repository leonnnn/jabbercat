import asyncio
import functools

import aioxmpp.structs

import mlxc.client
import mlxc.config
import mlxc.main
import mlxc.instrumentable_list
import mlxc.utils

import mlxcqt.model_adaptor as model_adaptor
import mlxcqt.roster

from . import Qt, utils, client
from .ui.dlg_account_manager import Ui_dlg_account_manager
from .ui.dlg_account_editor import Ui_dlg_account_editor
from .ui.roster import Ui_roster_window

from .custom_presence_states import DlgCustomPresenceStates
from .input_jid import DlgInputJID


class DlgAccountEditor(Qt.QDialog, Ui_dlg_account_editor):
    def __init__(self, dlg_account_manager, account):
        super().__init__(parent=dlg_account_manager)
        self.mlxc = dlg_account_manager.mlxc
        self.accounts = dlg_account_manager.accounts
        self.account = account

        self.setupUi(self)

        self.acc_password_warning.setVisible(
            not self.accounts.keyring_is_safe
        )

        self._modified = False
        utils.asyncify(utils.block_widget_for_coro)(self, self._reset())

    @asyncio.coroutine
    def _reset(self):
        try:
            password = yield from self.accounts.get_stored_password(
                self.account.jid
            )
            self.acc_password.setText(password or "")
            self.acc_save_password.setChecked(bool(password))
        except mlxc.client.PasswordStoreIsUnsafe:
            self.acc_save_password.setChecked(False)
            self.acc_save_password.setEnabled(False)

        self.acc_require_encryption.setChecked(
            not self.account.allow_unencrypted
        )

        if self.account.override_peer:
            self.acc_override_host.setText(
                self.account.override_peer.host or ""
            )
            self.acc_override_port.setValue(
                self.account.override_peer.port or 5222
            )
        else:
            self.acc_override_host.setText("")
            self.acc_override_port.setValue(5222)

        self.acc_jid.setText(str(self.account.jid))
        self.acc_resource.setText(self.account.resource)

    @asyncio.coroutine
    def _save(self):
        if     (self.acc_save_password.checkState() == Qt.Qt.Checked and
                self.acc_password.text()):
            try:
                yield from self.accounts.set_stored_password(
                    self.account.jid,
                    self.acc_password.text(),
                )
            except mlxc.client.PasswordStoreIsUnsafe:
                pass
        else:
            try:
                yield from self.accounts.set_stored_password(
                    self.account.jid,
                    None)
            except mlxc.client.PasswordStoreIsUnsafe:
                pass

        self.account.allow_unencrypted = (
            self.acc_require_encryption.checkState() != Qt.Qt.Checked
        )

        self.account.resource = self.acc_resource.text() or None

        if self.acc_override_host.text():
            self.account.override_peer = mlxc.client.ConnectionOverride()
            self.account.override_peer.host = self.acc_override_host.text()
            self.account.override_peer.port = self.acc_override_port.value()
        else:
            self.account.override_peer = None

    @utils.asyncify_blocking
    @asyncio.coroutine
    def accept(self):
        yield from self._save()
        super().accept()


class DlgAccountManager(Qt.QDialog, Ui_dlg_account_manager):
    def __init__(self, main_window):
        super().__init__()
        self.mlxc = main_window.mlxc
        self.accounts = self.mlxc.client.accounts

        self.setupUi(self)
        self.setModal(False)

        btn = self.button_box.button(Qt.QDialogButtonBox.Close)
        btn.setAutoDefault(False)
        btn.setDefault(False)

        self.model_wrapper = Qt.QSortFilterProxyModel()
        self.model_wrapper.setSourceModel(self.accounts.qmodel)
        self.model_wrapper.setSortLocaleAware(True)
        self.model_wrapper.setSortCaseSensitivity(False)
        self.model_wrapper.setSortRole(Qt.Qt.DisplayRole)
        self.model_wrapper.setDynamicSortFilter(True)

        self.account_list.setModel(self.model_wrapper)
        self.account_list.setSelectionBehavior(Qt.QTableView.SelectRows);
        self.account_list.setSelectionMode(Qt.QTableView.SingleSelection);
        self.account_list.setSortingEnabled(True)
        self.account_list.sortByColumn(0, Qt.Qt.AscendingOrder)

        self.account_list.activated.connect(self._account_list_activated)

        self.acc_add_existing.setDefaultAction(
            self.action_add_existing_account
        )
        self.acc_delete.setDefaultAction(
            self.action_delete_selected_account
        )

        self.action_add_existing_account.triggered.connect(
            self._on_add_existing_account
        )
        self.action_delete_selected_account.triggered.connect(
            self._on_delete_selected_account
        )

        self._modified = False

    @utils.asyncify
    @asyncio.coroutine
    def _account_list_activated(self, index):
        if not index.isValid():
            return

        index = self.model_wrapper.mapToSource(index)
        account = self.accounts[index.row()]

        dlg = DlgAccountEditor(self, account)
        yield from utils.exec_async(dlg)

    @utils.asyncify
    @asyncio.coroutine
    def _on_add_existing_account(self, checked):
        jid = yield from DlgInputJID(
            self.tr("Add registered account"),
            self.tr("Input the bare Jabber ID of the account you have"),
            self).run()
        if jid is None:
            return

        account = self.accounts.new_account(jid)

    @utils.asyncify
    @asyncio.coroutine
    def _on_delete_selected_account(self, checked):
        index = self.account_list.selectionModel().currentIndex()
        if not index.isValid():
            return
        index = self.model_wrapper.mapToSource(index)

        account = self.accounts[index.row()]

        msgbox = Qt.QMessageBox(
            Qt.QMessageBox.Warning,
            self.tr("Delete account"),
            self.tr("""\
Are you sure you want to delete the account {jid}?

This will delete all local information related to the account, but leave the account on the server untouched.""".format(jid=account.jid)),
            Qt.QMessageBox.Yes | Qt.QMessageBox.No,
            self)
        msgbox.setWindowModality(Qt.Qt.WindowModal)
        result = yield from utils.exec_async(msgbox)
        if result == Qt.QMessageBox.Yes:
            self.accounts.remove_account(account)


class RosterWindow(Qt.QMainWindow, Ui_roster_window):
    def __init__(self, main):
        super().__init__()

        self.mlxc = main
        self.account_manager = DlgAccountManager(self)
        self.custom_presence_states = DlgCustomPresenceStates(self)

        self.setupUi(self)

        self.action_quit.triggered.connect(
            self._on_quit)
        self.action_account_manager.triggered.connect(
            self._on_account_manager)
        self.action_edit_custom_presence_states.triggered.connect(
            self._on_custom_presence_states)

        self.action_open_command_prompt.triggered.connect(
            self.mlxc.open_command_prompt
        )
        print(self.action_open_command_prompt)
        self.action_open_command_prompt.setParent(self)
        self.action_open_command_prompt.setShortcuts([
            Qt.QKeySequence("Alt+x"),
            Qt.QKeySequence(":"),
        ])
        self.addAction(self.action_open_command_prompt)
        print(self.actions())
        print(self.action_open_command_prompt.isEnabled())
        print(self.action_open_command_prompt.shortcuts())
        print(self.action_open_command_prompt.associatedWidgets())

        self.presence_states_qmodel = utils.JoinedListsModel(
            utils.DictItemModel(mlxc.instrumentable_list.ModelList([
                {
                    "flags": Qt.Qt.ItemIsEnabled,
                    Qt.Qt.DisplayRole: "Set all accounts to",
                    Qt.Qt.AccessibleDescriptionRole: "separator",
                },
                {
                    Qt.Qt.DisplayRole: "Free for chat",
                    Qt.Qt.UserRole: aioxmpp.structs.PresenceState(
                        available=True,
                        show="chat"),
                },
                {
                    Qt.Qt.DisplayRole: "Available",
                    Qt.Qt.UserRole: aioxmpp.structs.PresenceState(
                        available=True,
                        show=None),
                },
                {
                    Qt.Qt.DisplayRole: "Away",
                    Qt.Qt.UserRole: aioxmpp.structs.PresenceState(
                        available=True,
                        show="away"),
                },
                {
                    Qt.Qt.DisplayRole: "Not available",
                    Qt.Qt.UserRole: aioxmpp.structs.PresenceState(
                        available=True,
                        show="xa"),
                },
                {
                    Qt.Qt.DisplayRole: "Do not disturb",
                    Qt.Qt.UserRole: aioxmpp.structs.PresenceState(
                        available=True,
                        show="dnd"),
                },
                {
                    Qt.Qt.DisplayRole: "Offline",
                    Qt.Qt.UserRole: aioxmpp.structs.PresenceState(),
                },
                {
                    "flags": Qt.Qt.ItemIsEnabled,
                    Qt.Qt.DisplayRole: "Custom configuration",
                    Qt.Qt.AccessibleDescriptionRole: "separator",
                }

            ])),
            self.mlxc.client.presence_states_qmodel
        )
        self.presence_state_selector.setModel(
            self.presence_states_qmodel
        )
        self.presence_state_selector.setCurrentIndex(6)
        self.presence_state_selector.activated.connect(
            self._on_presence_state_changed)

        self.mlxc.client.summon(mlxc.roster.Plugin)

        roster_model = mlxcqt.roster.RosterTreeModel(
            self.mlxc.client.roster,
            parent=self)
        self.roster_view.setModel(roster_model)

    def _on_quit(self):
        self.mlxc.main.quit()

    def _on_account_manager(self):
        self.account_manager.show()

    def _on_custom_presence_states(self):
        self.custom_presence_states.show()

    def _on_presence_state_changed(self, index):
        state = self.presence_states_qmodel.data(
            self.presence_states_qmodel.index(index),
            Qt.Qt.UserRole
        )

        if isinstance(state, aioxmpp.structs.PresenceState):
            state = mlxc.client.FundamentalPresenceState(state)

        self.mlxc.client.apply_presence_state(state)

    def closeEvent(self, event):
        result = super().closeEvent(event)
        self.mlxc.main.quit()
        return result


class CommandPromptPopup(Qt.QTreeWidget):
    def __init__(self):
        super().__init__()
        self.setRootIsDecorated(False)
        self.setWindowFlags(Qt.Qt.ToolTip)

        self.setMinimumSize(Qt.QSize(400, 100))
        self.setMaximumSize(Qt.QSize(730, 350))

        self.header().setVisible(False)


class CommandPrompt(Qt.QLineEdit):
    def __init__(self):
        super().__init__()
        abort_shortcut = Qt.QShortcut(Qt.QKeySequence("Escape"), self)
        abort_shortcut.activated.connect(
            self._abort
        )
        abort_shortcut.setContext(Qt.Qt.ApplicationShortcut)

        self._popup = CommandPromptPopup()
        self._popup.installEventFilter(self)
        self.installEventFilter(self)

    def _wait_for_confirm(self):
        def triggered(*args):
            nonlocal fut, triggered
            fut.set_result(None)

        def disconnect(fut):
            nonlocal triggered
            self.returnPressed.disconnect(triggered)

        fut = asyncio.Future()
        fut.add_done_callback(disconnect)
        self.returnPressed.connect(triggered)
        return fut

    def _close(self):
        self.setParent(None)
        self._popup.hide()

    def eventFilter(self, obj, ev):
        if ev.type() == Qt.QEvent.FocusOut:
            print(ev)
            if not self.hasFocus() and not self._popup.hasFocus():
                self._abort()
        return super().eventFilter(obj, ev)

    def focusEvent(self, ev):
        if ev.type() == Qt.QEvent.FocusIn:
            self._popup.show()
        return super().focusEvent(ev)

    def _show_popup(self):
        rect = self.geometry()
        below = self.mapToGlobal(Qt.QPoint(0, self.height()))
        above = self.mapToGlobal(Qt.QPoint(0, 0))

        screen_space = Qt.QApplication.desktop().availableGeometry(
            Qt.QApplication.desktop().screenNumber(self)
        )
        space_below = screen_space.height() - below.y()
        space_above = above.y() - screen_space.y()

        min_size = self._popup.minimumSize()
        max_size = self._popup.maximumSize()

        # try to place it below the input first

        if min_size.height() < space_below:
            final_rect = Qt.QRect(
                below.x(), below.y(),
                min_size.width(), min(space_below, max_size.height())
            )
        elif min_size.height() < space_above:
            height = min(space_above, max_size.height())
            final_rect = Qt.QRect(
                above.x(), above.y() - height,
                min_size.width(), height,
            )
        else:
            final_rect = Qt.QRect(
                above.x(), 0,
                min_size.width(), screen_space.height()
            )

        width = min(screen_space.width(), max_size.width())
        final_rect.setWidth(width)
        if final_rect.right() >= screen_space.right():
            final_rect.setRight(screen_space.right())
            final_rect.setLeft(final_rect.right() - width)

        self._popup.setGeometry(final_rect)
        self._popup.show()

    @asyncio.coroutine
    def _prompt(self):
        self.setText("")
        self._show_popup()
        yield from self._wait_for_confirm()
        self._close()

    def open_at_window(self, window):
        if self.parent() is not None:
            raise RuntimeError("Command prompt is already open")

        if isinstance(window, Qt.QMainWindow):
            parent = window.centralWidget()
        else:
            parent = window

        parent.layout().addWidget(self)
        self.setFocus()
        self._task = mlxc.utils.logged_async(
            self._prompt(),
            name="command prompt"
        )

    def _abort(self):
        self._task.cancel()
        self._close()


class MLXCQt:
    def __init__(self, main, event_loop):
        self.main = main
        self.loop = event_loop
        self.client = client.Client(mlxc.config.make_config_manager())
        self.roster = RosterWindow(self)
        self._command_prompt = CommandPrompt()

    def open_command_prompt(self):
        if self._command_prompt.parent() is not None:
            return
        active_window = Qt.QApplication.activeWindow()
        self._command_prompt.open_at_window(active_window)

    @asyncio.coroutine
    def run(self, main_future):
        self.client.load_state()
        self.roster.show()
        yield from main_future
        self.client.config_manager.writeback()


class QtMain(mlxc.main.Main):
    @asyncio.coroutine
    def run_core(self):
        mlxc = MLXCQt(self, self.loop)
        yield from mlxc.run(self.main_future)
        del mlxc
