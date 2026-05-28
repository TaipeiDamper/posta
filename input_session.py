"""Application-level input image state."""

from image_io import align_image_to_base, normalize_to_bgra


class InputSession:
    def __init__(self):
        self.images = []
        self.base_size = None
        self.global_image = None

    def get_global_image(self):
        return self.global_image

    def get_image(self, idx):
        if 0 <= idx < len(self.images):
            return self.images[idx]
        return None

    def set_global_image(self, img):
        normalized = normalize_to_bgra(img)
        if normalized is None:
            return None

        self.global_image = normalized.copy()
        h, w = self.global_image.shape[:2]
        self.base_size = (w, h)
        if self.images:
            self.images[0] = self.global_image
        else:
            self.images = [self.global_image]
        return self.global_image

    def append_import_image(self, img):
        normalized = normalize_to_bgra(img)
        if normalized is None:
            return None, None

        h, w = normalized.shape[:2]
        if self.base_size is None:
            self.base_size = (w, h)
        processed, _ = align_image_to_base(normalized, self.base_size)
        idx = len(self.images)
        self.images.append(processed)
        self.global_image = processed
        return idx, processed

    def clear(self):
        self.images.clear()
        self.base_size = None
        self.global_image = None

    def bind_node_to_global(self, node):
        node.set_external_image_source(self.get_global_image)

    def bind_node_to_index(self, node, idx):
        node.set_external_image_source(lambda idx=idx: self.get_image(idx))
