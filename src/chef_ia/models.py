"""Modelos simples que representan el conocimiento de Chef IA."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document

from .ingredient_catalog import IngredientCatalog


@dataclass(frozen=True, slots=True)
class Recipe:
    """Una receta autorizada extraída de la Biblioteca de Recetas."""

    name: str
    meal_type: str
    preparation_time: str
    difficulty: str
    ingredients: tuple[str, ...]
    steps: tuple[str, ...]
    recommendation: str


@dataclass(frozen=True, slots=True)
class KnowledgeBase:
    """Información consolidada a partir de los documentos del proyecto."""

    recipes: tuple[Recipe, ...]
    prompt_rules: str
    policy_text: str
    source_files: tuple[Path, ...]
    documents: tuple[Document, ...]
    ingredient_catalog: IngredientCatalog


@dataclass(frozen=True, slots=True)
class UserRequest:
    """Datos obligatorios que una persona proporciona para recibir una receta."""

    ingredients: tuple[str, ...]
    meal_type: str
    servings: int
