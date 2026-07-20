"""Pruebas de carga y reglas de negocio con la biblioteca estándar."""

from pathlib import Path
import unittest

from chef_ia.knowledge import KnowledgeLoader
from chef_ia.service import ChefIAService, NoMatchingRecipeError, RequestValidationError
from chef_ia.retriever import KnowledgeRetriever
from chef_ia.agent import CohereChefAgent


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIRECTORY = PROJECT_ROOT.parent


class ChefIATests(unittest.TestCase):
    """Verifica que el agente solo use conocimiento autorizado."""

    @classmethod
    def setUpClass(cls) -> None:
        """Carga los documentos reales una sola vez para todas las pruebas."""

        cls.knowledge = KnowledgeLoader().load(DATA_DIRECTORY)
        cls.service = ChefIAService(cls.knowledge)

    def test_loads_the_twenty_authorized_recipes(self) -> None:
        """La biblioteca entregada contiene exactamente veinte recetas."""

        self.assertEqual(20, len(self.knowledge.recipes))
        self.assertEqual(7, len(self.knowledge.documents))
        self.assertEqual(15, len(self.knowledge.ingredient_catalog.chile_varieties))

    def test_retriever_returns_project_context(self) -> None:
        """El recuperador local encuentra contenido sobre recetas sin usar una API."""

        results = KnowledgeRetriever(self.knowledge.documents).search("tinga de pollo")
        self.assertTrue(results)
        self.assertIn("Tinga de pollo", results[0].page_content)

    def test_requires_all_conversation_data(self) -> None:
        """No se acepta una solicitud sin ingredientes, tipo o personas válidas."""

        with self.assertRaises(RequestValidationError):
            self.service.create_request("", "comida", "2")
        with self.assertRaises(RequestValidationError):
            self.service.create_request("pollo", "postre", "2")
        with self.assertRaises(RequestValidationError):
            self.service.create_request("pollo", "comida", "0")

    def test_recommends_only_a_matching_authorized_recipe(self) -> None:
        """Pollo para comida produce una receta de comida de la biblioteca."""

        request = self.service.create_request("pollo, jitomate, cebolla, chipotle", "comida", "2")
        recipe = self.service.recommend(request)
        self.assertIn(recipe.name, {item.name for item in self.knowledge.recipes})
        self.assertEqual("Comida", recipe.meal_type)

    def test_does_not_limit_recipe_by_meal_type(self) -> None:
        """Una receta de comida puede recomendarse aunque se indique desayuno."""

        request = self.service.create_request("pollo, chipotle", "desayuno", "2")
        self.assertEqual("Tinga de pollo", self.service.recommend(request).name)

    def test_rejects_unknown_ingredient_combinations(self) -> None:
        """No se inventa una receta cuando no hay coincidencias autorizadas."""

        request = self.service.create_request("salmón", "cena", "1")
        with self.assertRaises(NoMatchingRecipeError):
            self.service.recommend(request)

    def test_uses_documented_ingredient_replacements(self) -> None:
        """El catálogo permite completar una receta con ingredientes documentados."""

        request = self.service.create_request("pollo, jitomate, cebolla", "comida", "2")
        self.assertEqual("Tinga de pollo", self.service.recommend(request).name)

    def test_normalizes_an_exact_chile_variety_and_plural_forms(self) -> None:
        """El catálogo reconoce chile serrano, chile genérico y huevo/huevos."""

        catalog = self.knowledge.ingredient_catalog
        self.assertTrue(catalog.matches("chile serrano", "chiles"))
        self.assertTrue(catalog.matches("chile serrano", "serrano"))
        self.assertTrue(catalog.matches("huevo", "huevos"))

    def test_recommends_huevos_when_only_huevo_is_provided(self) -> None:
        """Los faltantes proceden del catálogo leído, no de listas manuales."""

        request = self.service.create_request("huevo", "cualquiera", "2")
        self.assertEqual("Huevos a la mexicana", self.service.recommend(request).name)

    def test_normalizes_generic_meat_and_its_documented_types(self) -> None:
        """Carne, res y cerdo se relacionan con las proteínas del documento."""

        catalog = self.knowledge.ingredient_catalog
        self.assertTrue(catalog.matches("carne de res", "carne"))
        self.assertTrue(catalog.matches("carne de res", "res"))
        self.assertTrue(catalog.matches("carne", "carne de cerdo"))
        request = self.service.create_request("carne", "cualquiera", "2")
        self.assertEqual("Carne con papas", self.service.recommend(request).name)

    def test_normalizes_a_common_category(self) -> None:
        """Las categorías de Ingredientes.docx también satisfacen sus integrantes."""

        catalog = self.knowledge.ingredient_catalog
        self.assertTrue(catalog.matches("jitomate", "verduras"))
        self.assertTrue(catalog.matches("pollo", "proteína"))

    def test_accepts_generic_chile_for_a_chile_variety(self) -> None:
        """“Chiles” satisface la categoría de chile usada en la tinga."""

        request = self.service.create_request("pollo, jitomate, chiles", "cualquiera", "2")
        self.assertEqual("Tinga de pollo", self.service.recommend(request).name)

    def test_allows_basic_extras_and_authorized_condiments(self) -> None:
        """Aceite y sal pueden complementar los huevos a la mexicana."""

        request = self.service.create_request(
            "huevos, jitomate, cebolla, chile serrano", "desayuno", "1"
        )
        self.assertEqual("Huevos a la mexicana", self.service.recommend(request).name)

    def test_rejects_an_unknown_primary_ingredient(self) -> None:
        """No ofrece opciones si el primer ingrediente no aparece en la biblioteca."""

        request = self.service.create_request("salmón", "comida", "1")
        with self.assertRaises(NoMatchingRecipeError):
            self.service.recommend(request)

    def test_returns_three_options_using_the_first_ingredient(self) -> None:
        """Pollo como primer ingrediente prioriza alternativas que incluyen pollo."""

        request = self.service.create_request("pollo, jitomate, chiles", "cualquiera", "2")
        options = self.service.recommend_options(request)
        self.assertEqual("Tinga de pollo", options[0].name)
        self.assertLessEqual(len(options), 3)
        self.assertTrue(all("pollo" in " ".join(recipe.ingredients).casefold() for recipe in options))

    def test_keeps_only_the_final_cohere_text_block(self) -> None:
        """Los bloques internos no se muestran a la persona usuaria."""

        response = [
            {"type": "thinking", "thinking": "Internal English reasoning."},
            {"type": "text", "text": "Respuesta final en español."},
        ]
        self.assertEqual("Respuesta final en español.", CohereChefAgent._final_text(response))


if __name__ == "__main__":
    unittest.main()
