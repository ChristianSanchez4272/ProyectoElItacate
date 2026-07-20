"""Normalización de ingredientes basada exclusivamente en Ingredientes.docx."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


def normalize_ingredient(value: str) -> str:
    """Convierte texto a minúsculas, sin acentos y con espacios uniformes."""

    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFD", value.casefold())
        if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"\s+", " ", without_accents).strip()


@dataclass(frozen=True, slots=True)
class IngredientCatalog:
    """Catálogo, alias y categorías construidos desde Ingredientes.docx."""

    chile_varieties: tuple[str, ...]
    cheese_varieties: tuple[str, ...]
    common_ingredients: tuple[str, ...]
    condiments: tuple[str, ...]
    common_categories: dict[str, tuple[str, ...]]
    aliases: dict[str, str]
    categories: dict[str, frozenset[str]]
    documented_ingredients: frozenset[str]

    @classmethod
    def from_sections(
        cls,
        chile_varieties: tuple[str, ...],
        cheese_varieties: tuple[str, ...],
        common_ingredients: tuple[str, ...],
        condiments: tuple[str, ...],
        common_categories: dict[str, tuple[str, ...]],
    ) -> "IngredientCatalog":
        """Crea índices de comparación sin depender de listas en el servicio."""

        aliases: dict[str, str] = {}

        def register(value: str) -> str:
            canonical = normalize_ingredient(value)
            aliases[canonical] = canonical
            if len(canonical) > 3 and canonical.endswith("s"):
                aliases[canonical[:-1]] = canonical
            if len(canonical) > 4 and canonical.endswith("es"):
                aliases[canonical[:-2]] = canonical
            return canonical

        chile_members = {register(item) for item in chile_varieties}
        cheese_members = {register(item) for item in cheese_varieties}
        common_members = {register(item) for item in common_ingredients}
        condiment_members = {register(item) for item in condiments}
        normalized_common_categories = {
            normalize_ingredient(category): frozenset(register(item) for item in members)
            for category, members in common_categories.items()
        }

        categories: dict[str, frozenset[str]] = {
            "chile": frozenset(chile_members),
            "queso": frozenset(cheese_members),
            **normalized_common_categories,
        }
        for category in categories:
            register(category)

        # Las formas cortas se derivan de nombres completos que aparecen en el documento.
        for chile in chile_members:
            aliases[chile.removeprefix("chile ")] = chile
        for cheese in cheese_members:
            aliases[cheese.removeprefix("queso ")] = cheese

        # "Carne" agrupa únicamente res y cerdo, que son las carnes explícitas del documento.
        meat_members = frozenset(
            member
            for member in normalized_common_categories.get("proteinas", frozenset())
            if member.startswith("carne de ")
        )
        if meat_members:
            categories["carne"] = meat_members
            aliases["carne"] = "carne"
            for meat in meat_members:
                aliases[meat.removeprefix("carne de ")] = meat

        # Equivalencias lingüísticas seguras; no son sustituciones culinarias inventadas.
        for alias, canonical in {
            "tomate": "jitomate",
            "aceite vegetal": "aceite",
            "pollo deshebrado": "pollo",
            "tortilla": "tortillas",
            "frijol": "frijoles",
        }.items():
            normalized_canonical = normalize_ingredient(canonical)
            if normalized_canonical in common_members:
                aliases[normalize_ingredient(alias)] = normalized_canonical

        documented = frozenset(
            chile_members | cheese_members | common_members | condiment_members | set(categories)
        )
        return cls(
            chile_varieties=chile_varieties,
            cheese_varieties=cheese_varieties,
            common_ingredients=common_ingredients,
            condiments=condiments,
            common_categories=common_categories,
            aliases=aliases,
            categories=categories,
            documented_ingredients=documented,
        )

    def canonicalize(self, value: str) -> str:
        """Obtiene el nombre canónico o conserva una entrada no documentada."""

        normalized = normalize_ingredient(value)
        direct = self.aliases.get(normalized)
        if direct is not None:
            return direct
        if len(normalized) > 3 and normalized.endswith("s"):
            return self.aliases.get(normalized[:-1], normalized)
        return normalized

    def matches(self, required: str, supplied: str) -> bool:
        """Comprueba coincidencia exacta o relación con una categoría documentada."""

        canonical_required = self.canonicalize(required)
        canonical_supplied = self.canonicalize(supplied)
        if canonical_required == canonical_supplied:
            return True
        required_category = self.categories.get(canonical_required)
        if required_category is not None and canonical_supplied in required_category:
            return True
        supplied_category = self.categories.get(canonical_supplied)
        return supplied_category is not None and canonical_required in supplied_category

    def is_documented(self, value: str) -> bool:
        """Indica si el ingrediente puede agregarse desde Ingredientes.docx."""

        return self.canonicalize(value) in self.documented_ingredients

    def is_condiment(self, value: str) -> bool:
        """Indica si se trata de un condimento opcional del documento."""

        return self.canonicalize(value) in {
            self.canonicalize(item) for item in self.condiments
        }
