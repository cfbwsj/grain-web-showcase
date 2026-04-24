from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from .config import settings


ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff]")

ZH_TO_EN = {
    "\u5168\u8eab": "full body",
    "\u534a\u8eab": "half body",
    "\u7279\u5199": "close-up",
    "\u7ea2\u8272": "red",
    "\u7ea2": "red",
    "\u84dd\u8272": "blue",
    "\u84dd": "blue",
    "\u7eff\u8272": "green",
    "\u7eff": "green",
    "\u9ec4\u8272": "yellow",
    "\u9ec4": "yellow",
    "\u9ed1\u8272": "black",
    "\u9ed1": "black",
    "\u767d\u8272": "white",
    "\u767d": "white",
    "\u7070\u8272": "gray",
    "\u7070": "gray",
    "\u68d5\u8272": "brown",
    "\u68d5": "brown",
    "\u7d2b\u8272": "purple",
    "\u7d2b": "purple",
    "\u7c89\u8272": "pink",
    "\u7c89": "pink",
    "\u6a59\u8272": "orange",
    "\u6a59": "orange",
    "\u4e0a\u8863": "top",
    "\u5916\u5957": "jacket",
    "\u5939\u514b": "jacket",
    "\u77ed\u8896": "short sleeve shirt",
    "\u957f\u8896": "long sleeve shirt",
    "\u886c\u886b": "shirt",
    "\u536b\u8863": "hoodie",
    "\u8fde\u8863\u88d9": "dress",
    "\u88d9\u5b50": "skirt",
    "\u88e4\u5b50": "pants",
    "\u725b\u4ed4\u88e4": "jeans",
    "\u77ed\u88e4": "shorts",
    "\u978b": "shoes",
    "\u9774\u5b50": "boots",
    "\u80cc\u5305": "backpack",
    "\u4e66\u5305": "backpack",
    "\u5305": "bag",
    "\u624b\u63d0\u5305": "handbag",
    "\u884c\u674e\u7bb1": "suitcase",
    "\u884c\u674e": "luggage",
    "\u5e3d\u5b50": "hat",
    "\u773c\u955c": "glasses",
    "\u53e3\u7f69": "mask",
    "\u56f4\u5dfe": "scarf",
    "\u957f\u53d1": "long hair",
    "\u77ed\u53d1": "short hair",
    "\u7537\u4eba": "man",
    "\u7537\u6027": "man",
    "\u7537": "man",
    "\u5973\u4eba": "woman",
    "\u5973\u6027": "woman",
    "\u5973": "woman",
    "\u884c\u4eba": "person",
    "\u4eba": "person",
    "\u82d2\u679c": "mango",
    "\u9999\u8549": "banana",
    "\u82f9\u679c": "apple",
    "\u6a59\u5b50": "orange fruit",
    "\u68a8": "pear",
    "\u8461\u8404": "grape",
    "\u897f\u74dc": "watermelon",
    "\u83e0\u841d": "pineapple",
    "\u8349\u8393": "strawberry",
    "\u6843\u5b50": "peach",
    "\u6c34\u679c": "fruit",
    "\u6c7d\u8f66": "car",
    "\u8f66\u8f86": "vehicle",
    "\u51fa\u79df\u8f66": "taxi",
    "\u5361\u8f66": "truck",
    "\u516c\u4ea4\u8f66": "bus",
    "\u516c\u4ea4": "bus",
    "\u706b\u8f66": "train",
    "\u9ad8\u94c1": "high-speed train",
    "\u5730\u94c1": "subway",
    "\u98de\u673a": "airplane",
    "\u81ea\u884c\u8f66": "bicycle",
    "\u7535\u52a8\u8f66": "electric bike",
    "\u6469\u6258\u8f66": "motorcycle",
    "\u8239": "boat",
    "\u624b\u673a": "phone",
    "\u7535\u8111": "computer",
    "\u7b14\u8bb0\u672c": "laptop",
    "\u76f8\u673a": "camera",
    "\u676f\u5b50": "cup",
    "\u74f6\u5b50": "bottle",
    "\u96e8\u4f1e": "umbrella",
    "\u6905\u5b50": "chair",
    "\u51f3\u5b50": "table",
    "\u6c99\u53d1": "sofa",
    "\u76d2\u5b50": "box",
    "\u95e8": "door",
    "\u7a97\u6237": "window",
    "\u8def\u724c": "sign",
    "\u6807\u724c": "sign",
    "\u5efa\u7b51": "building",
    "\u697c": "building",
    "\u8857\u9053": "street",
    "\u9053\u8def": "road",
    "\u6865": "bridge",
    "\u8f66\u7ad9": "station",
    "\u5730\u94c1\u7ad9": "subway station",
    "\u673a\u573a": "airport",
    "\u6559\u5ba4": "classroom",
    "\u529e\u516c\u5ba4": "office",
    "\u5546\u573a": "mall",
    "\u5546\u5e97": "store",
    "\u8d85\u5e02": "supermarket",
    "\u5e7f\u573a": "square",
    "\u6d77\u6ee9": "beach",
    "\u5c71": "mountain",
    "\u6cb3": "river",
    "\u6811": "tree",
    "\u82b1": "flower",
    "\u8349": "grass",
    "\u5929\u7a7a": "sky",
    "\u8001\u864e": "tiger",
    "\u72ee\u5b50": "lion",
    "\u8c79\u5b50": "leopard",
    "\u718a\u732b": "panda",
    "\u72d7\u718a": "bear",
    "\u718a": "bear",
    "\u5927\u8c61": "elephant",
    "\u7334\u5b50": "monkey",
    "\u6591\u9a6c": "zebra",
    "\u957f\u9888\u9e7f": "giraffe",
    "\u9a6c": "horse",
    "\u9a86\u9a7c": "camel",
    "\u725b": "cow",
    "\u7f8a": "sheep",
    "\u732a": "pig",
    "\u5154\u5b50": "rabbit",
    "\u732b": "cat",
    "\u72d7": "dog",
    "\u9e1f": "bird",
}


def contains_cjk(text: str) -> bool:
    return bool(CJK_CHAR_RE.search(text or ""))


def _count_cjk_chars(text: str) -> int:
    return len(CJK_CHAR_RE.findall(text or ""))


def _ordered_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    lowered_ascii = [token.lower() for token in ASCII_TOKEN_RE.findall(text or "")]
    normalized_text = re.sub(r"[，。！？、；：,.!?;:/\\()\[\]{}]+", " ", text or "")
    working_text = normalized_text

    for zh, en in sorted(ZH_TO_EN.items(), key=lambda item: len(item[0]), reverse=True):
        if zh in working_text and en not in tokens:
            tokens.append(en)
            working_text = working_text.replace(zh, " ")

    for token in lowered_ascii:
        if token not in tokens:
            tokens.append(token)

    return tokens


def _pick_translation_device() -> str:
    requested = settings.translation_device or "cpu"
    if requested != "auto":
        return requested
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


@lru_cache(maxsize=1)
def _load_transformers_translator() -> tuple[Any, Any, str]:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(settings.translation_model_name)
    model = AutoModelForSeq2SeqLM.from_pretrained(settings.translation_model_name)
    device = _pick_translation_device()
    if device != "cpu":
        model = model.to(device)
    model.eval()
    return tokenizer, model, device


def _translate_with_transformers(text: str) -> str | None:
    import torch

    tokenizer, model, device = _load_transformers_translator()
    inputs = tokenizer(
        [text],
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=128,
    )
    if device != "cpu":
        inputs = {key: value.to(device) for key, value in inputs.items()}
    with torch.no_grad():
        generated = model.generate(
            **inputs,
            max_new_tokens=settings.translation_max_new_tokens,
            num_beams=settings.translation_num_beams,
            early_stopping=True,
        )
    translated = tokenizer.batch_decode(generated, skip_special_tokens=True)[0].strip()
    translated = re.sub(r"\s+", " ", translated)
    return translated or None


def _translate_with_dictionary(text: str) -> str | None:
    tokens = _ordered_tokens(text)
    if not tokens:
        return None
    has_person = any(
        token in tokens for token in {"person", "man", "woman", "full body", "half body"}
    )
    prefix = "a full body photo of" if has_person else "a photo of"
    prompt = f"{prefix} {' '.join(tokens)}".strip()
    return re.sub(r"\s+", " ", prompt)


def _should_prefer_dictionary(text: str, dictionary_prompt: str | None) -> bool:
    if not dictionary_prompt:
        return False
    cjk_count = _count_cjk_chars(text)
    ascii_count = len(ASCII_TOKEN_RE.findall(text or ""))
    compact_text = re.sub(r"\s+", "", text or "")
    # Short noun-like Chinese queries are usually translated more reliably by
    # a direct lexical mapping than by a generative model.
    return cjk_count > 0 and cjk_count <= 4 and ascii_count == 0 and len(compact_text) <= 4


def normalize_for_retrieval(text: str) -> tuple[str, str]:
    """Return an English-oriented retrieval prompt and the provider name."""
    text = (text or "").strip()
    if not text:
        return "", "none"
    if not contains_cjk(text):
        return text, "original"

    dictionary_prompt = _translate_with_dictionary(text)
    if _should_prefer_dictionary(text, dictionary_prompt):
        return dictionary_prompt or text, "local-zh-dictionary-priority"

    backend = settings.translation_backend
    if backend in {"transformers", "marian", "model", "auto"}:
        try:
            translated = _translate_with_transformers(text)
            if translated and not contains_cjk(translated):
                return translated, "transformers-marian"
        except Exception:
            if backend != "auto":
                if dictionary_prompt:
                    return dictionary_prompt, "local-zh-dictionary-fallback"

    if dictionary_prompt:
        return dictionary_prompt, "local-zh-dictionary"

    return text, "local-cjk-fallback"
