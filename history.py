"""Undo / Redo 歷史堆疊。"""


class HistoryManager:
    def __init__(self, get_state, restore_state, max_depth=30):
        self._get_state = get_state
        self._restore_state = restore_state
        self.max_depth = max_depth
        self.history = []
        self.redo_stack = []
        self._is_restoring = False

    @property
    def is_restoring(self):
        return self._is_restoring

    def save_state(self):
        if self._is_restoring:
            return
        self.history.append(self._get_state())
        self.redo_stack.clear()
        if len(self.history) > self.max_depth:
            self.history.pop(0)

    def undo(self):
        if len(self.history) <= 1:
            return
        self.redo_stack.append(self.history.pop())
        self._is_restoring = True
        try:
            self._restore_state(self.history[-1])
        finally:
            self._is_restoring = False

    def redo(self):
        if not self.redo_stack:
            return
        nxt = self.redo_stack.pop()
        self.history.append(nxt)
        self._is_restoring = True
        try:
            self._restore_state(nxt)
        finally:
            self._is_restoring = False

    def push_initial(self):
        self.save_state()

    def restore_quiet(self, state):
        """還原狀態且不觸發 save_state（用於匯入範本等）。"""
        self._is_restoring = True
        try:
            self._restore_state(state)
        finally:
            self._is_restoring = False
