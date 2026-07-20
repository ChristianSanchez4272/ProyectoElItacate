"""Reglas de negocio para conversar y recomendar recetas autorizadas."""

from __future__ import annotations

from fractions import Fraction
import re

from .ingredient_catalog import IngredientCatalog, normalize_ingredient
from .models import KnowledgeBase, Recipe, UserRequest


# Se conserva para clientes anteriores; ya no se usa para limitar recetas.
ALLOWED_MEAL_TYPES = {"desayuno", "comida", "cena", "antojito", "cualquiera"}
QUANTITY = re.compile(r"^(?P<amount>\d+(?:/\d+)?)\s+(?P<name>.+)$")


class RequestValidationError(ValueError):
    """Indica que faltan datos obligatorios o que estos no cumplen las reglas."""


class NoMatchingRecipeError(LookupError):
    """Indica que ninguna receta autorizada coincide con la solicitud."""


class ChefIAService:
    """Selecciona recetas de la biblioteca usando el catálogo de Ingredientes.docx."""

    def __init__(self, knowledge: KnowledgeBase) -> None:
        """Guarda la base de conocimiento ya validada."""

        self._knowledge = knowledge

    @property
    def policy_text(self) -> str:
        """Expone las políticas para mostrarlas antes de iniciar la conversación."""

        return self._knowledge.policy_text

    def create_request(
        self, ingredients_text: str, meal_type: str, servings_text: str
    ) -> UserRequest:
        """Valida ingredientes y personas; el tipo se conserva por compatibilidad."""

        ingredients = tuple(
            ingredient.strip() for ingredient in ingredients_text.split(",") if ingredient.strip()
        )
        if not ingredients:
            raise RequestValidationError("Indica al menos un ingrediente disponible.")

        normalized_type = normalize_ingredient(meal_type)
        if normalized_type not in ALLOWED_MEAL_TYPES:
            allowed = ", ".join(sorted(ALLOWED_MEAL_TYPES))
            raise RequestValidationError(f"El tipo de platillo debe ser: {allowed}.")

        try:
            servings = int(servings_text)
        except ValueError as error:
            raise RequestValidationError("El número de personas debe ser un entero positivo.") from error
        if servings < 1:
            raise RequestValidationError("El número de personas debe ser mayor que cero.")
        return UserRequest(ingredients, normalized_type, servings)

    def recommend(self, request: UserRequest) -> Recipe:
        """Conserva compatibilidad al devolver la primera opción recomendada."""

        return self.recommend_options(request, limit=1)[0]

    def recommend_options(self, request: UserRequest, limit: int = 3) -> tuple[Recipe, ...]:
        """Devuelve hasta tres recetas cuyo primer ingrediente sea la base."""

        catalog = self._knowledge.ingredient_catalog
        available = {catalog.canonicalize(item) for item in request.ingredients}
        primary_ingredient = catalog.canonicalize(request.ingredients[0])
        candidates = [
            (position, recipe)
            for position, recipe in enumerate(self._knowledge.recipes)
            if self._recipe_uses_primary_ingredient(recipe, primary_ingredient, catalog)
            and self._can_complete_with_documented_replacements(recipe, available, catalog)
        ]
        if not candidates:
            raise NoMatchingRecipeError(
                f"No encontré una receta autorizada cuyo ingrediente principal sea “{request.ingredients[0]}”. "
                "Los ingredientes faltantes solo pueden completarse con Ingredientes.docx."
            )
        ranked = sorted(
            candidates,
            key=lambda item: (-self._user_ingredient_count(item[1], available, catalog), item[0]),
        )
        return tuple(recipe for _, recipe in ranked[:limit])

    def select_option(self, request: UserRequest, recipe_name: str) -> Recipe:
        """Obtiene una opción mostrada previamente y rechaza nombres no autorizados."""

        for recipe in self.recommend_options(request):
            if recipe.name == recipe_name:
                return recipe
        raise RequestValidationError("La receta elegida no pertenece a las opciones disponibles.")

    def render_recipe(self, recipe: Recipe, request: UserRequest) -> str:
        """Genera una respuesta local con el formato obligatorio del proyecto."""

        ingredients = "\n".join(
            f"- {self._scale_ingredient(item, request.servings)}" for item in recipe.ingredients
        )
        steps = "\n".join(f"{index}. {step}" for index, step in enumerate(recipe.steps, start=1))
        condiments = ", ".join(self._knowledge.ingredient_catalog.condiments)
        return (
            f"Nombre del platillo: {recipe.name}\n"
            f"Tiempo aproximado: {recipe.preparation_time}\n"
            f"Nivel de dificultad: {recipe.difficulty}\n\n"
            f"Ingredientes para {request.servings} persona(s):\n{ingredients}\n\n"
            f"Procedimiento paso a paso:\n{steps}\n\n"
            f"Recomendaciones finales:\n{recipe.recommendation}\n"
            f"Condimentos opcionales del documento: {condiments}, al gusto.\n"
            "Lava tus manos y utensilios, verifica el buen estado de los alimentos y cocina completamente carnes, pollo y huevo.\n\n"
            "¡Buen provecho! Gracias por cocinar con El Itacate. ¡Cocinando con IA!"
        )

    def _can_complete_with_documented_replacements(
        self, recipe: Recipe, available: set[str], catalog: IngredientCatalog
    ) -> bool:
        """Comprueba que cada faltante figure en el catálogo autorizado."""

        return all(
            any(
                any(catalog.matches(option, supplied) for supplied in available)
                or catalog.is_documented(option)
                for option in alternatives
            )
            for alternatives in _required_ingredient_options(recipe, catalog)
        )

    @staticmethod
    def _recipe_uses_primary_ingredient(
        recipe: Recipe, primary_ingredient: str, catalog: IngredientCatalog
    ) -> bool:
        """Comprueba que el primer ingrediente de la persona aparezca en la receta."""

        return any(
            catalog.matches(option, primary_ingredient)
            for alternatives in _required_ingredient_options(recipe, catalog)
            for option in alternatives
        )

    @staticmethod
    def _user_ingredient_count(
        recipe: Recipe, available: set[str], catalog: IngredientCatalog
    ) -> int:
        """Cuenta grupos de la receta que aportó directamente la persona usuaria."""

        return sum(
            any(
                catalog.matches(option, supplied)
                for option in alternatives
                for supplied in available
            )
            for alternatives in _required_ingredient_options(recipe, catalog)
        )

    @staticmethod
    def _scale_ingredient(ingredient: str, servings: int) -> str:
        """Escala cantidades numéricas y conserva indicaciones sin cantidad."""

        match = QUANTITY.match(ingredient)
        if match is None or servings == 1:
            return ingredient
        amount = Fraction(match.group("amount")) * servings
        number = str(amount.numerator) if amount.denominator == 1 else f"{amount.numerator}/{amount.denominator}"
        return f"{number} {match.group('name')}"


def _remove_quantity(value: str) -> str:
    """Elimina el prefijo numérico para comparar nombres de ingredientes."""

    match = QUANTITY.match(value)
    return match.group("name") if match else value


def _required_ingredient_options(
    recipe: Recipe, catalog: IngredientCatalog
) -> tuple[tuple[str, ...], ...]:
    """Agrupa alternativas separadas por “o” y excluye opcionales y condimentos."""

    groups: list[tuple[str, ...]] = []
    for ingredient in recipe.ingredients:
        value = normalize_ingredient(_remove_quantity(ingredient))
        if "opcional" in value:
            continue
        for required in value.split(" y "):
            options = tuple(option.strip() for option in required.split(" o ") if option.strip())
            required_options = tuple(option for option in options if not catalog.is_condiment(option))
            if required_options:
                groups.append(required_options)
    return tuple(groups)
