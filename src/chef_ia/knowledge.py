"""Carga los documentos de El Itacate y transforma la biblioteca en recetas."""

from __future__ import annotations

from pathlib import Path
import re

from .docx_reader import read_paragraphs
from .document_loader import load_directory
from .ingredient_catalog import IngredientCatalog, normalize_ingredient
from .models import KnowledgeBase, Recipe


REQUIRED_DOCUMENTS = (
    "Base_de_Conocimiento_Chef_IA.docx",
    "Biblioteca_de_Recetas_Chef_IA.docx",
    "Manual_Generacion_Recetas_Chef_IA.docx",
    "Politicas_de_Uso_El_Itacate.docx",
    "Presentacion_Proyecto_El_Itacate.docx",
    "Prompt_Maestro_Chef_IA.docx",
    "Ingredientes.docx",
)
RECIPE_HEADING = re.compile(r"^(\d+)\.\s+(.+)$")


class KnowledgeLoadError(RuntimeError):
    """Indica que faltan documentos o que la biblioteca no tiene recetas válidas."""


class KnowledgeLoader:
    """Lee una vez los documentos requeridos y construye una base de conocimiento."""

    def load(self, data_directory: Path) -> KnowledgeBase:
        """Carga todos los documentos requeridos desde ``data_directory``."""

        directory = data_directory.resolve()
        paths = tuple(directory / name for name in REQUIRED_DOCUMENTS)
        missing = [path.name for path in paths if not path.is_file()]
        if missing:
            raise KnowledgeLoadError("Faltan documentos requeridos: " + ", ".join(missing))

        content = {path.name: read_paragraphs(path) for path in paths}
        documents = load_directory(directory)
        recipes = self._parse_recipes(content["Biblioteca_de_Recetas_Chef_IA.docx"])
        if not recipes:
            raise KnowledgeLoadError("No se encontraron recetas en la biblioteca.")

        return KnowledgeBase(
            recipes=recipes,
            prompt_rules="\n".join(content["Prompt_Maestro_Chef_IA.docx"]),
            policy_text="\n".join(content["Politicas_de_Uso_El_Itacate.docx"]),
            source_files=paths,
            documents=documents,
            ingredient_catalog=self._parse_ingredient_catalog(content["Ingredientes.docx"]),
        )

    @staticmethod
    def _parse_ingredient_catalog(paragraphs: tuple[str, ...]) -> IngredientCatalog:
        """Lee secciones y subcategorías de Ingredientes.docx sin datos codificados."""

        chiles: list[str] = []
        cheeses: list[str] = []
        common: list[str] = []
        condiments: list[str] = []
        common_categories: dict[str, list[str]] = {}
        section = ""
        common_subsection = ""
        common_headers = {
            "verduras", "frutas", "proteinas", "leguminosas", "cereales", "lacteos", "condimentos",
        }
        for line in paragraphs:
            normalized = normalize_ingredient(line)
            if normalized.startswith("1. chiles"):
                section = "chiles"
                continue
            if normalized.startswith("2. quesos"):
                section = "quesos"
                continue
            if normalized.startswith("3. ingredientes comunes"):
                section = "comunes"
                continue
            if normalized.startswith("4. reglas"):
                break

            if section == "chiles" and line.casefold().startswith("chile "):
                chiles.append(line)
            elif section == "quesos" and line.casefold().startswith("queso "):
                cheeses.append(line)
            elif section == "comunes":
                if normalized in common_headers:
                    common_subsection = normalized
                elif common_subsection == "condimentos":
                    condiments.append(line)
                elif common_subsection:
                    common.append(line)
                    common_categories.setdefault(common_subsection, []).append(line)

        return IngredientCatalog.from_sections(
            tuple(chiles),
            tuple(cheeses),
            tuple(common),
            tuple(condiments),
            {category: tuple(items) for category, items in common_categories.items()},
        )

    @staticmethod
    def _parse_recipes(paragraphs: tuple[str, ...]) -> tuple[Recipe, ...]:
        """Convierte cada sección numerada de la biblioteca en una receta estructurada."""

        start_indexes = [
            index
            for index, line in enumerate(paragraphs[:-1])
            if RECIPE_HEADING.match(line)
            and paragraphs[index + 1].casefold() == "tipo de platillo"
        ]
        recipes: list[Recipe] = []
        for position, start in enumerate(start_indexes):
            match = RECIPE_HEADING.match(paragraphs[start])
            if match is None:
                continue
            end = start_indexes[position + 1] if position + 1 < len(start_indexes) else len(paragraphs)
            section = paragraphs[start + 1 : end]
            fields = KnowledgeLoader._recipe_fields(section)
            if {"tipo de platillo", "ingredientes principales", "procedimiento"} - fields.keys():
                continue
            recipes.append(
                Recipe(
                    name=match.group(2).strip(),
                    meal_type=fields["tipo de platillo"],
                    preparation_time=fields.get("tiempo aproximado", "No indicado"),
                    difficulty=fields.get("dificultad", "No indicada"),
                    ingredients=tuple(KnowledgeLoader._split_ingredients(fields["ingredientes principales"])),
                    steps=tuple(KnowledgeLoader._split_steps(fields["procedimiento"])),
                    recommendation=fields.get("recomendación", "Servir recién preparado."),
                )
            )
        return tuple(recipes)

    @staticmethod
    def _recipe_fields(section: tuple[str, ...]) -> dict[str, str]:
        """Obtiene pares etiqueta/valor de una sección de receta."""

        labels = {
            "tipo de platillo",
            "tiempo aproximado",
            "dificultad",
            "ingredientes principales",
            "procedimiento",
            "recomendación",
        }
        fields: dict[str, str] = {}
        for index, line in enumerate(section[:-1]):
            normalized = line.casefold()
            if normalized in labels:
                fields[normalized] = section[index + 1]
        return fields

    @staticmethod
    def _split_ingredients(value: str) -> list[str]:
        """Separa la lista de ingredientes conservando el texto original."""

        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _split_steps(value: str) -> list[str]:
        """Separa pasos numerados que aparecen en una sola línea del documento."""

        steps = re.split(r"(?=\d+\.\s)", value)
        return [re.sub(r"^\d+\.\s*", "", step).strip() for step in steps if step.strip()]
