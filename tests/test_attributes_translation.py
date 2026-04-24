from app.attributes import compose_attribute_prompt
from app.translation import normalize_for_retrieval


def test_chinese_query_normalizes_to_english_terms():
    query, provider = normalize_for_retrieval("穿红色上衣背黑色背包的男性")
    assert provider == "local-cjk-dictionary"
    assert "red" in query
    assert "black" in query
    assert "backpack" in query
    assert "man" in query


def test_attribute_prompt_is_search_sentence():
    prompt = compose_attribute_prompt(
        {
            "gender": "woman",
            "top_color": "blue",
            "top_type": "jacket",
            "bottom_color": "black",
            "bottom_type": "pants",
            "accessory": "bag",
        }
    )
    assert "woman" in prompt
    assert "blue jacket" in prompt
    assert "black pants" in prompt
    assert "bag" in prompt

