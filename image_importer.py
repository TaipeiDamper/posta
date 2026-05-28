"""圖片匯入流程：剪貼簿、檔案選擇與拖曳檔案共用同一條路徑。"""

import os
import traceback

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QTextEdit,
)

from core_nodes import ImageInputNode
from image_io import bgra_to_qpixmap, clipboard_rgba_to_bgra, normalize_to_bgra
from ui_graphics import NodeItem


SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}


def read_image_file(path):
    """使用 OpenCV 讀取路徑，保留 alpha，並支援 Windows 非 ASCII 路徑。"""
    try:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    except Exception:
        return None
    return normalize_to_bgra(img)


def image_paths_from_mime(mime_data):
    if mime_data is None or not mime_data.hasUrls():
        return []

    paths = []
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        path = url.toLocalFile()
        if os.path.splitext(path)[1].lower() in SUPPORTED_IMAGE_EXTENSIONS:
            paths.append(path)
    return paths


def mime_has_image_paths(mime_data):
    return bool(image_paths_from_mime(mime_data))


def mime_has_importable_image(mime_data):
    return bool(mime_data and (mime_data.hasImage() or mime_has_image_paths(mime_data)))


def image_data_to_bgra(image_data):
    if isinstance(image_data, QPixmap):
        image_data = image_data.toImage()
    if not isinstance(image_data, QImage):
        return None
    img, _, _ = clipboard_rgba_to_bgra(image_data)
    return img


class ImageImportManager:
    """把匯入副作用集中在這裡，MainWindow 僅負責 UI 事件轉接。"""

    def __init__(
        self,
        input_session,
        scene,
        graph,
        add_node,
        set_preview_image,
        request_evaluate,
        show_status,
    ):
        self.input_session = input_session
        self.scene = scene
        self.graph = graph
        self.add_node = add_node
        self.set_preview_image = set_preview_image
        self.request_evaluate = request_evaluate
        self.show_status = show_status

    def load_original_from_dialog(self, parent):
        fname, _ = QFileDialog.getOpenFileName(
            parent,
            "開啟原圖",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff)",
        )
        if not fname:
            return False

        img = read_image_file(fname)
        if img is None:
            self._show_status("無法讀取影像檔案")
            return False

        self.set_global_image(img)
        self._show_status(f"已載入原圖：{os.path.basename(fname)}", 2000)
        return True

    def paste_from_clipboard(self):
        if self._paste_into_focused_text_widget():
            return True

        clipboard = QApplication.clipboard()
        mime_data = clipboard.mimeData()
        if mime_data.hasImage():
            new_img, _, _ = clipboard_rgba_to_bgra(clipboard.image())
            if new_img is None:
                return False
            return self.import_image_as_input(new_img, source_label="剪貼簿")

        paths = image_paths_from_mime(mime_data)
        if paths:
            return self.import_paths(paths)

        return False

    def import_paths(self, paths):
        imported = 0
        for path in paths:
            img = read_image_file(path)
            if img is None:
                self._show_status(f"無法讀取影像檔案：{os.path.basename(path)}")
                continue
            if self.import_image_as_input(img, source_label=os.path.basename(path), show_status=False):
                imported += 1

        if imported:
            self._show_status(f"已匯入 {imported} 張影像", 2000)
            return True
        return False

    def import_from_mime(self, mime_data):
        if mime_data and mime_data.hasImage():
            img = image_data_to_bgra(mime_data.imageData())
            if img is not None:
                return self.import_image_as_input(img, source_label="拖曳影像")
        return self.import_paths(image_paths_from_mime(mime_data))

    def import_image_as_input(self, img, source_label="影像", show_status=True):
        new_img = normalize_to_bgra(img)
        if new_img is None:
            return False

        try:
            with self.scene.graph_lock():
                img_idx, processed_img = self.input_session.append_import_image(new_img)
                if processed_img is None:
                    return False
                n_item = None
                if img_idx == 0:
                    n_item = self._first_input_node_item()

            if not n_item:
                n_item = self.add_node("輸入 (Input)")

            with self.scene.graph_lock():
                if n_item:
                    self.input_session.bind_node_to_index(n_item.node_model, img_idx)
                self.graph.mark_all_dirty()

            self.set_preview_image(bgra_to_qpixmap(processed_img))
            self.request_evaluate()
        except Exception as exc:
            traceback.print_exc()
            print(f"圖片匯入失敗: {exc}")
            return False

        if show_status:
            self._show_status(f"已匯入影像：{source_label}", 2000)
        return True

    def set_global_image(self, img):
        try:
            with self.scene.graph_lock():
                global_img = self.input_session.set_global_image(img)
                if global_img is None:
                    return False
                self._sync_input_nodes_to_global()
                self.graph.mark_all_dirty()

            self.set_preview_image(bgra_to_qpixmap(global_img))
            self.request_evaluate()
            return True
        except Exception as exc:
            traceback.print_exc()
            print(f"設定原圖失敗: {exc}")
            return False

    def clear_input_image(self):
        with self.scene.graph_lock():
            self.input_session.clear()
            self.graph.mark_all_dirty()
        self.request_evaluate()

    def _first_input_node_item(self):
        for item in self.scene.items():
            if isinstance(item, NodeItem) and isinstance(item.node_model, ImageInputNode):
                return item
        return None

    def _sync_input_nodes_to_global(self):
        for item in self.scene.items():
            if isinstance(item, NodeItem) and isinstance(item.node_model, ImageInputNode):
                self.input_session.bind_node_to_global(item.node_model)

    def _show_status(self, message, timeout=3000):
        self.show_status(message, timeout)

    def _paste_into_focused_text_widget(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit)):
            focus.paste()
            return True
        if isinstance(focus, QSpinBox):
            if focus.lineEdit():
                focus.lineEdit().paste()
            return True
        return False
