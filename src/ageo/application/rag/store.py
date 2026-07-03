"""RAG-lite: bundled GIS recipes grounding the plan composer.

Per the brief (section 14), RAG supports the workflow machinery, never
replaces it, and must not be a startup dependency: this store loads
bundled JSON recipes lazily and scores them by keyword overlap. A
pgvector-backed store can implement the same search() signature later;
if it is unavailable the system falls back to exactly this.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

# Turkish-aware folding, shared spirit with the planner.
_TR_FOLD = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u",
})


def _fold(text: str) -> str:
    return text.translate(_TR_FOLD).lower()


@dataclass(frozen=True)
class Recipe:
    name: str
    keywords: tuple[str, ...]
    guidance: str  # the text injected into the composer prompt


class RecipeStore:
    def __init__(self, recipes: tuple[Recipe, ...] | None = None) -> None:
        self._recipes = recipes

    def search(self, text: str, k: int = 2) -> list[str]:
        """Return the guidance texts of the k best keyword-matching recipes."""
        recipes = self._recipes if self._recipes is not None else _bundled()
        folded = _fold(text)
        scored = [
            (sum(1 for kw in recipe.keywords if _fold(kw) in folded), recipe)
            for recipe in recipes
        ]
        scored = [(score, recipe) for score, recipe in scored if score > 0]
        scored.sort(key=lambda item: item[0], reverse=True)
        return [recipe.guidance for _, recipe in scored[:k]]


@lru_cache(maxsize=1)
def _bundled() -> tuple[Recipe, ...]:
    payload = json.loads(
        resources.files("ageo.application.rag")
        .joinpath("bundled_recipes.json")
        .read_text(encoding="utf-8")
    )
    return tuple(
        Recipe(
            name=item["name"],
            keywords=tuple(item["keywords"]),
            guidance=item["guidance"],
        )
        for item in payload["recipes"]
    )
