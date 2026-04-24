from __future__ import annotations

from .translation import ZH_TO_EN


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return ZH_TO_EN.get(text, text).strip().lower()


def compose_attribute_prompt(attributes: dict[str, object]) -> str:
    gender = _clean(attributes.get("gender")) or "person"
    age = _clean(attributes.get("age"))
    top_color = _clean(attributes.get("top_color"))
    top_type = _clean(attributes.get("top_type")) or "top"
    bottom_color = _clean(attributes.get("bottom_color"))
    bottom_type = _clean(attributes.get("bottom_type"))
    shoes_color = _clean(attributes.get("shoes_color"))
    accessory = _clean(attributes.get("accessory"))
    action = _clean(attributes.get("action"))
    scene = _clean(attributes.get("scene"))
    extra = _clean(attributes.get("extra"))

    subject = " ".join(part for part in [age, gender] if part)
    clauses = [f"a full body photo of a {subject}".strip()]
    if top_color or top_type:
        clauses.append(f"wearing a {' '.join(p for p in [top_color, top_type] if p)}")
    if bottom_color or bottom_type:
        clauses.append(f"with {' '.join(p for p in [bottom_color, bottom_type] if p)}")
    if shoes_color:
        clauses.append(f"wearing {shoes_color} shoes")
    if accessory:
        clauses.append(f"carrying or wearing {accessory}")
    if action:
        clauses.append(action)
    if scene:
        clauses.append(f"in {scene}")
    if extra:
        clauses.append(extra)

    return " ".join(clauses)

