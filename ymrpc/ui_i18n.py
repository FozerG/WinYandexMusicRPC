"""Small Qt bindings for translating existing widgets without recreating them."""

from PyQt6.QtCore import QObject, Qt
from PyQt6.QtWidgets import QComboBox, QListWidget, QMessageBox

from .i18n import tr

TEXT_ROLE = Qt.ItemDataRole.UserRole + 1
PROPERTY_PREFIX = "i18n_"


def bind_text(widget, key: str, setter: str = "setText"):
    widget.setProperty(PROPERTY_PREFIX + setter, key)
    getattr(widget, setter)(tr(key))
    return widget


def retranslate(root: QObject) -> None:
    for widget in [root, *root.findChildren(QObject)]:
        for property_name in widget.dynamicPropertyNames():
            name = bytes(property_name).decode()
            if name.startswith(PROPERTY_PREFIX):
                getattr(widget, name[len(PROPERTY_PREFIX) :])(tr(widget.property(name)))
        if isinstance(widget, QComboBox):
            blocked = widget.blockSignals(True)
            try:
                for index in range(widget.count()):
                    key = widget.itemData(index, TEXT_ROLE)
                    if key:
                        widget.setItemText(index, tr(key))
            finally:
                widget.blockSignals(blocked)
        elif isinstance(widget, QListWidget):
            for index in range(widget.count()):
                item = widget.item(index)
                key = item.data(TEXT_ROLE)
                if key:
                    item.setText(tr(key))


def show_message(parent, title: str, text: str, icon=QMessageBox.Icon.Information):
    """Translate our own dialog button independently of Qt's installed locale."""
    dialog = QMessageBox(icon, title, text, parent=parent)
    dialog.addButton(tr("common.ok"), QMessageBox.ButtonRole.AcceptRole)
    return dialog.exec()
