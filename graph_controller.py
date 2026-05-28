"""Graph scene mutation coordination.

This keeps QGraphics items from reaching back into MainWindow for mutexes or
application state. UI code receives this small controller explicitly instead.
"""

from contextlib import nullcontext
from dataclasses import dataclass
from typing import Callable, Optional

from PySide6.QtCore import QMutexLocker


@dataclass
class GraphSceneController:
    mutex: object | None = None
    on_node_removed: Optional[Callable[[object], None]] = None

    def lock(self):
        if self.mutex is None:
            return nullcontext()
        return QMutexLocker(self.mutex)

    def node_removed(self, node):
        if self.on_node_removed:
            self.on_node_removed(node)
