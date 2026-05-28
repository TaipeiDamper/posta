"""圖評估：防抖排程與可選背景執行緒骨架（revision 取消語意）。"""

from PySide6.QtCore import QObject, QMutex, QMutexLocker, QThread, Signal, Slot


class _EvaluateWorker(QThread):
    finished_revision = Signal(int)

    def __init__(self, graph, revision, mutex):
        super().__init__()
        self._graph = graph
        self._revision = revision
        self._mutex = mutex

    def run(self):
        with QMutexLocker(self._mutex):
            self._graph.evaluate()
        self.finished_revision.emit(self._revision)


class GraphEvaluator(QObject):
    """在主執行緒套用結果；背景 evaluate 以 mutex 保護 graph。"""

    evaluation_done = Signal(int)

    def __init__(self, graph, parent=None):
        super().__init__(parent)
        self._graph = graph
        self._mutex = QMutex()
        self._revision = 0
        self._pending_revision = 0
        self._worker = None
        # 背景執行緒保留為內部骨架；預設同步評估，避免無事件迴圈測試或關閉時遺留 QThread。
        self._use_background = False

    def bump_revision(self):
        self._revision += 1
        return self._revision

    @property
    def mutex(self):
        return self._mutex

    def evaluate_sync(self):
        with QMutexLocker(self._mutex):
            self._graph.evaluate()

    def request_background_evaluate(self):
        rev = self.bump_revision()
        self._pending_revision = rev
        if self._worker and self._worker.isRunning():
            return rev
        self._worker = _EvaluateWorker(self._graph, rev, self._mutex)
        self._worker.finished_revision.connect(self._on_worker_finished)
        self._worker.start()
        return rev

    @Slot(int)
    def _on_worker_finished(self, revision):
        if revision != self._pending_revision:
            return
        self.evaluation_done.emit(revision)

    def is_revision_current(self, revision):
        return revision == self._revision
