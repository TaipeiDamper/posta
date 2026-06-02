import sys
import numpy as np
import cv2

from core_engine import Graph
from core_nodes import ImageInputNode, MergeNode, TextNode, OutputNode

def test_proxy_scale():
    print("Testing proxy scale...")
    g = Graph()
    g.proxy_scale = 0.5
    
    # 建立輸入節點
    input_node = ImageInputNode()
    # 建立一個模擬的 100x100 影像
    dummy_img = np.ones((100, 100, 4), dtype=np.uint8) * 128
    input_node.set_external_image_source(lambda: dummy_img)
    g.add_node(input_node)
    
    # 建立輸出節點
    output_node = OutputNode()
    g.add_node(output_node)
    
    # 連接
    output_node.inputs["Image In"].connect(input_node.outputs["Image Out"])
    
    # 評估
    g.evaluate()
    
    final_img = output_node.final_image
    assert final_img is not None, "Final image should not be None"
    h, w = final_img.shape[:2]
    print(f"Proxy scale 0.5: Original size 100x100 -> Output size {w}x{h}")
    assert w == 50 and h == 50, f"Expected size 50x50, got {w}x{h}"
    print("Proxy scale test passed!")

def test_merge_node_overflow():
    print("Testing MergeNode overflow fix...")
    # 建立兩個測試影像，讓 alpha_out 非常小或是產生大數值
    base = np.zeros((10, 10, 4), dtype=np.uint8)
    base[:,:,:3] = 255 # 白色
    base[:,:,3] = 1   # 極低不透明度
    
    overlay = np.zeros((10, 10, 4), dtype=np.uint8)
    overlay[:,:,:3] = 255 # 白色
    overlay[:,:,3] = 1   # 極低不透明度
    
    node = MergeNode()
    # 進行 process
    res = node.process(**{"Base In": base, "Overlay In": overlay})
    img = res["Image Out"]
    
    assert img is not None
    print(f"Merge output pixel RGB sample: {img[0,0,:3]}")
    # 檢查 RGB 是否依然是正確的 255，且沒有發生溢位數值反轉
    assert np.all(img[:,:,:3] == 255), f"Expected RGB to be 255, got {img[0,0,:3]}"
    print("MergeNode overflow test passed!")

def test_text_node_transparent_bg():
    print("Testing TextNode transparent background...")
    node = TextNode()
    node.params["text"] = "Test"
    node.params["text_color_rgb"] = [255, 0, 0] # 紅色文字
    
    res = node.process(**{"Image In": None})
    img = res["Image Out"]
    
    assert img is not None
    assert img.shape == (512, 512, 4)
    # 檢查背景的 alpha 通道是否在沒有文字的地方是 0 (透明)
    alpha = img[:,:,3]
    total_transparent = np.sum(alpha == 0)
    total_text = np.sum(alpha > 0)
    print(f"Transparent pixels: {total_transparent}, Text pixels: {total_text}")
    assert total_transparent > 0, "Should have transparent background"
    assert total_text > 0, "Should have text pixels"
    
    # 檢查文字顏色是否是紅色 (bgr = (0, 0, 255))
    text_pixel_colors = img[alpha > 0, :3]
    max_red = np.max(text_pixel_colors[:, 2]) # R 通道
    min_blue = np.min(text_pixel_colors[:, 0]) # B 通道
    min_green = np.min(text_pixel_colors[:, 1]) # G 通道
    assert max_red == 255 and min_blue == 0 and min_green == 0, f"Expected red color text, got sample colors: {text_pixel_colors[0]}"
    print("TextNode transparent background test passed!")

def test_mask_invert_node_registry():
    print("Testing MaskInvertNode registry and resolve_key...")
    from node_registry import resolve_registry_key, NODE_MAP
    # 測試括號解析邏輯是否能正確定位 Key
    key = resolve_registry_key("反向選取 (Mask Invert)")
    assert key == "Mask Invert", f"Expected 'Mask Invert', got {key}"
    display_name, cls = NODE_MAP[key]
    assert cls.__name__ == "MaskInvertNode", f"Expected MaskInvertNode, got {cls.__name__}"
    print("MaskInvertNode registry test passed!")

def test_mask_invert_node_mask_io():
    print("Testing MaskInvertNode mask input/output...")
    from core_nodes import MaskInvertNode

    node = MaskInvertNode()
    assert node.inputs["Mask In"].pin_type == "mask"
    assert node.outputs["Mask Out"].pin_type == "mask"

    mask = np.array([[0, 64], [128, 255]], dtype=np.uint8)
    result = node.process(**{"Mask In": mask})["Mask Out"]
    expected = np.array([[255, 191], [127, 0]], dtype=np.uint8)
    assert np.array_equal(result, expected), f"Expected inverted mask {expected}, got {result}"
    print("MaskInvertNode mask I/O test passed!")

def test_clear_input_state():
    print("Testing clear_input_image state clean...")
    # 模擬 MainWindow 清除狀態
    from main import MainWindow
    from PySide6.QtWidgets import QApplication
    import sys
    
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    
    # 模擬匯入一張測試圖
    dummy_img = np.ones((100, 100, 4), dtype=np.uint8) * 128
    win.set_global_image(dummy_img)
    
    assert win.global_input_image is not None
    assert len(win.input_images) > 0
    assert win.base_size == (100, 100)
    
    # 模擬點擊清除
    win.clear_input_image()
    
    assert win.global_input_image is None
    assert len(win.input_images) == 0
    assert win.base_size is None
    
    # 停用計時器並安全刪除以防止 GC 崩潰
    win.timer.stop()
    win._eval_timer.stop()
    win.deleteLater()
    
    print("clear_input_image state clean test passed!")

def test_bloom_node():
    print("Testing BloomNode...")
    from core_nodes import BloomNode
    node = BloomNode()
    node.params["threshold"] = 200
    node.params["blur_size"] = 3
    node.params["intensity"] = 100
    
    # 創建一個 5x5 的影像，只有正中間的點是超亮像素，其他是黑色
    img = np.zeros((5, 5, 4), dtype=np.uint8)
    img[:, :, 3] = 255
    img[2, 2, :3] = 255 # 亮點
    
    res = node.process(**{"Image In": img})
    out_img = res["Image Out"]
    
    assert out_img is not None
    # 檢查亮點周圍本來是黑色的像素，是否因為高斯模糊發光疊加後不再是 0
    assert out_img[2, 2, 0] == 255
    assert out_img[2, 1, 0] > 0, "Glow should spread to adjacent pixels"
    print("BloomNode test passed!")

def test_channel_split_merge_nodes():
    print("Testing ChannelSplitNode and ChannelMergeNode...")
    from core_nodes import ChannelSplitNode, ChannelMergeNode
    split_node = ChannelSplitNode()
    merge_node = ChannelMergeNode()
    
    # 建立一個測試用 BGRA 影像
    img = np.random.randint(0, 256, (10, 10, 4), dtype=np.uint8)
    
    # 進行拆分
    split_res = split_node.process(**{"Image In": img})
    r = split_res["R Out"]
    g = split_res["G Out"]
    b = split_res["B Out"]
    a = split_res["A Out"]
    
    assert r is not None and g is not None and b is not None and a is not None
    
    # 進行合併
    merge_res = merge_node.process(**{"R In": r, "G In": g, "B In": b, "A In": a})
    merged_img = merge_res["Image Out"]
    
    assert merged_img is not None
    assert np.array_equal(img, merged_img), "Roundtrip split and merge should reproduce original image exactly"
    print("ChannelSplitNode and ChannelMergeNode test passed!")

def test_apply_mask_node():
    print("Testing ApplyMaskNode...")
    from core_nodes import ApplyMaskNode
    node = ApplyMaskNode()
    
    # 建立 5x5 的隨機色彩影像 (Alpha = 255)
    img = np.random.randint(0, 256, (5, 5, 4), dtype=np.uint8)
    img[:, :, 3] = 255
    
    # 建立一個測試遮罩 (一部份 255，一部份 0)
    mask = np.zeros((5, 5), dtype=np.uint8)
    mask[1:4, 1:4] = 255
    
    res = node.process(**{"Image In": img, "Mask In": mask})
    out_img = res["Image Out"]
    
    assert out_img is not None
    # 驗證 RGB 是否未變動
    assert np.array_equal(img[:,:,:3], out_img[:,:,:3]), "RGB channels should not be modified by ApplyMaskNode"
    # 驗證 Alpha 通道是否與遮罩相同
    assert np.array_equal(out_img[:,:,3], mask), "Alpha channel should match the applied mask exactly"
    print("ApplyMaskNode test passed!")

def test_luma_midtone_param_meta():
    print("Testing Luma and Midtone param_meta range limits...")
    from core_nodes import LuminanceNode, MidtoneKeyNode
    from ui_components import ConfigPanel
    
    luma_node = LuminanceNode()
    midtone_node = MidtoneKeyNode()
    
    min_range_luma = ConfigPanel._numeric_range_for_key(luma_node, "range_min (%)", 0)
    max_range_luma = ConfigPanel._numeric_range_for_key(luma_node, "range_max (%)", 100)
    assert min_range_luma == (0, 100), f"Expected (0, 100), got {min_range_luma}"
    assert max_range_luma == (0, 100), f"Expected (0, 100), got {max_range_luma}"
    
    min_range_midtone = ConfigPanel._numeric_range_for_key(midtone_node, "range_min (%)", 0)
    max_range_midtone = ConfigPanel._numeric_range_for_key(midtone_node, "range_max (%)", 100)
    assert min_range_midtone == (0, 100), f"Expected (0, 100), got {min_range_midtone}"
    assert max_range_midtone == (0, 100), f"Expected (0, 100), got {max_range_midtone}"
    
    print("Luma and Midtone param_meta range limits test passed!")


if __name__ == "__main__":
    test_proxy_scale()
    test_merge_node_overflow()
    test_text_node_transparent_bg()
    test_mask_invert_node_registry()
    test_mask_invert_node_mask_io()
    test_clear_input_state()
    test_bloom_node()
    test_channel_split_merge_nodes()
    test_apply_mask_node()
    test_luma_midtone_param_meta()
    print("All tests passed successfully!")
