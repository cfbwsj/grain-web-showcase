from __future__ import annotations

import re


ZH_TO_EN = {
    "红色": "red",
    "红": "red",
    "蓝色": "blue",
    "蓝": "blue",
    "绿色": "green",
    "绿": "green",
    "黄色": "yellow",
    "黄": "yellow",
    "黑色": "black",
    "黑": "black",
    "白色": "white",
    "白": "white",
    "灰色": "gray",
    "灰": "gray",
    "棕色": "brown",
    "棕": "brown",
    "紫色": "purple",
    "紫": "purple",
    "粉色": "pink",
    "粉": "pink",
    "橙色": "orange",
    "橙": "orange",
    "上衣": "top",
    "外套": "jacket",
    "夹克": "jacket",
    "短袖": "short sleeve shirt",
    "长袖": "long sleeve shirt",
    "衬衫": "shirt",
    "裙子": "skirt",
    "连衣裙": "dress",
    "裤子": "pants",
    "牛仔裤": "jeans",
    "短裤": "shorts",
    "鞋": "shoes",
    "靴子": "boots",
    "背包": "backpack",
    "包": "bag",
    "帽子": "hat",
    "眼镜": "glasses",
    "口罩": "mask",
    "围巾": "scarf",
    "长发": "long hair",
    "短发": "short hair",
    "男人": "man",
    "男性": "man",
    "男": "man",
    "女人": "woman",
    "女性": "woman",
    "女": "woman",
    "行人": "person",
    "人": "person",
    "汽车": "car",
    "车辆": "vehicle",
    "自行车": "bicycle",
    "公交": "bus",
    "路牌": "sign",
    "建筑": "building",
    "树": "tree",
    "手机": "phone",
    "椅子": "chair",
}


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def normalize_for_retrieval(text: str) -> tuple[str, str]:
    """Return an English-ish query and the translation provider name."""
    text = (text or "").strip()
    if not text:
        return "", "none"
    if not contains_cjk(text):
        return text, "original"

    tokens: list[str] = []
    for zh, en in sorted(ZH_TO_EN.items(), key=lambda item: len(item[0]), reverse=True):
        if zh in text and en not in tokens:
            tokens.append(en)

    if not tokens:
        return text, "local-cjk-fallback"

    prefix = "a full body photo of" if any(t in tokens for t in {"person", "man", "woman"}) else "a photo of"
    return f"{prefix} {' '.join(tokens)}", "local-cjk-dictionary"

