"""OpenCV / NumPy 與 Qt 影像 I/O 共用工具。"""

import cv2
import numpy as np
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QApplication


def normalize_to_bgra(img):
    if img is None:
        return None
    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    if len(img.shape) == 3 and img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    if len(img.shape) == 3 and img.shape[2] == 4:
        return img
    return img


def bgra_to_qpixmap(img):
    h, w = img.shape[:2]
    rgba = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA))
    qimg = QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


def bgra_to_qimage(img):
    h, w = img.shape[:2]
    rgba = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA))
    return QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()


def clipboard_rgba_to_bgra(qimg):
    if qimg is None or qimg.isNull():
        return None, 0, 0
    qimg = qimg.convertToFormat(QImage.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    if w <= 0 or h <= 0:
        return None, w, h
    nbytes = qimg.sizeInBytes()
    if nbytes <= 0:
        return None, w, h
    qimg = qimg.copy()
    arr = np.frombuffer(qimg.bits(), dtype=np.uint8, count=nbytes)
    bpl = qimg.bytesPerLine()
    if bpl == w * 4:
        rgba = arr.reshape((h, w, 4))
    else:
        rgba = arr.reshape((h, bpl // 4, 4))[:, :w, :]
    return cv2.cvtColor(rgba.copy(), cv2.COLOR_RGBA2BGRA), w, h


def align_image_to_base(new_img, base_size):
    """依 base_size 平鋪或裁切對齊影像。"""
    h, w = new_img.shape[:2]
    if base_size is None:
        return new_img, (w, h)
    bw, bh = base_size
    if w == bw and h == bh:
        return new_img, base_size
    reps_h = (bh + h - 1) // h
    reps_w = (bw + w - 1) // w
    tiled = np.tile(new_img, (reps_h, reps_w, 1))
    sy = (tiled.shape[0] - bh) // 2
    sx = (tiled.shape[1] - bw) // 2
    return tiled[sy : sy + bh, sx : sx + bw].copy(), base_size


def copy_bgra_to_clipboard(img):
    qimg = bgra_to_qimage(img)
    QApplication.clipboard().setImage(qimg)
