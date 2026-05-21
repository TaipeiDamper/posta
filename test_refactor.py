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

if __name__ == "__main__":
    test_proxy_scale()
    test_merge_node_overflow()
    test_text_node_transparent_bg()
    print("All tests passed successfully!")
