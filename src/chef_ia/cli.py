"""Interfaz de terminal para usar Chef IA de forma guiada."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .agent import CohereChefAgent
from .knowledge import KnowledgeLoadError, KnowledgeLoader
from .retriever import KnowledgeRetriever
from .service import ChefIAService, NoMatchingRecipeError, RequestValidationError
from .settings import ConfigurationError, CohereSettings


def main() -> None:
    """Carga el conocimiento y ejecuta una conversación única con Chef IA."""

    # Las políticas incluyen caracteres como la casilla de aceptación. UTF-8 evita
    # que terminales de Windows con una página de códigos antigua fallen al mostrarlas.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Chef IA de El Itacate")
    parser.add_argument("--data-dir", default=".", help="Carpeta que contiene los documentos DOCX.")
    parser.add_argument(
        "--show-knowledge",
        action="store_true",
        help="Muestra el resultado de la lectura sin iniciar la conversación.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Genera una respuesta determinista sin llamar a Cohere.",
    )
    arguments = parser.parse_args()

    try:
        knowledge = KnowledgeLoader().load(Path(arguments.data_dir))
    except KnowledgeLoadError as error:
        parser.error(str(error))

    if arguments.show_knowledge:
        print(f"Documentos cargados: {len(knowledge.source_files)}")
        print(f"Recetas autorizadas: {len(knowledge.recipes)}")
        print("Todas las recetas autorizadas pueden usarse en cualquier momento.")
        return

    service = ChefIAService(knowledge)
    print("Hola, soy Chef IA de El Itacate. Cocinando con IA.\n")
    print("Políticas de Uso y Exención de Responsabilidad:\n")
    print(service.policy_text)
    print("\nDebes aceptar estas políticas antes de continuar.")
    if input("¿Aceptas las políticas? (sí/no): ").strip().casefold() not in {"si", "sí", "s"}:
        print("No es posible usar Chef IA sin aceptar las Políticas de Uso.")
        return

    print("\n¿Qué ingredientes tienes disponibles? Escríbelos separados por comas.")
    ingredients = input("> ")
    servings = input("¿Para cuántas personas cocinarás?\n> ")

    try:
        request = service.create_request(ingredients, "cualquiera", servings)
        recipe = service.recommend(request)
    except (RequestValidationError, NoMatchingRecipeError) as error:
        print(f"\nChef IA: {error}")
        return

    print("\nChef IA:\n")
    if arguments.offline:
        print(service.render_recipe(recipe, request))
        return

    try:
        agent = CohereChefAgent(CohereSettings.from_environment(), KnowledgeRetriever(knowledge.documents))
        print(agent.answer(recipe, request))
    except ConfigurationError as error:
        print(f"\nChef IA: {error}")
