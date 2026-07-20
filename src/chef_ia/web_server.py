"""Servidor web ligero para usar Chef IA desde la vista HTML."""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import threading
from typing import Any
from urllib.parse import urlparse

from .agent import CohereChefAgent
from .knowledge import KnowledgeLoader
from .models import Recipe
from .service import ChefIAService, NoMatchingRecipeError, RequestValidationError
from .settings import CohereSettings, ConfigurationError


PROJECT_DIRECTORY = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = PROJECT_DIRECTORY.parent
MAX_REQUEST_BYTES = 8_192


class RecipeSummary:
    """Datos mínimos que la vista necesita para presentar una opción de receta."""

    def __init__(self, name: str, preparation_time: str, difficulty: str) -> None:
        """Guarda los campos visibles sin exponer información interna de la receta."""

        self.name = name
        self.preparation_time = preparation_time
        self.difficulty = difficulty

    @classmethod
    def from_recipe(cls, recipe: Recipe) -> "RecipeSummary":
        """Construye el resumen a partir de una receta autorizada."""

        return cls(recipe.name, recipe.preparation_time, recipe.difficulty)

    def as_dict(self) -> dict[str, str]:
        """Convierte el resumen al formato JSON de la API."""

        return {
            "name": self.name,
            "preparation_time": self.preparation_time,
            "difficulty": self.difficulty,
        }


class AgentRuntime:
    """Mantiene cargado el conocimiento y crea el agente de Cohere bajo demanda."""

    def __init__(self, data_directory: Path) -> None:
        """Carga los documentos una vez para evitar trabajo repetido por petición."""

        knowledge = KnowledgeLoader().load(data_directory)
        self._service = ChefIAService(knowledge)
        self._knowledge = knowledge
        self._agent: CohereChefAgent | None = None
        self._agent_lock = threading.Lock()
        self._answer_lock = threading.Lock()

    @property
    def policy_text(self) -> str:
        """Devuelve las políticas que deben aceptarse antes de usar el chat."""

        return self._service.policy_text

    def options(self, ingredients: str, servings: str) -> tuple[RecipeSummary, ...]:
        """Devuelve hasta tres recetas para que la persona elija una."""

        request = self._service.create_request(ingredients, "cualquiera", servings)
        return tuple(RecipeSummary.from_recipe(recipe) for recipe in self._service.recommend_options(request))

    def answer(self, ingredients: str, servings: str, recipe_name: str) -> str:
        """Valida la opción elegida y pide a Cohere explicar esa receta."""

        request = self._service.create_request(ingredients, "cualquiera", servings)
        recipe = self._service.select_option(request, recipe_name)
        agent = self._get_agent()
        # El cliente de LangChain se usa de forma secuencial para conservar la
        # estabilidad del agente compartido en este servidor sencillo.
        with self._answer_lock:
            return agent.answer(recipe, request)

    def _get_agent(self) -> CohereChefAgent:
        """Inicializa el agente solo al recibir la primera consulta válida."""

        if self._agent is None:
            with self._agent_lock:
                if self._agent is None:
                    settings = CohereSettings.from_environment()
                    from .retriever import KnowledgeRetriever

                    self._agent = CohereChefAgent(
                        settings,
                        KnowledgeRetriever(self._knowledge.documents),
                    )
        return self._agent


class ChefIARequestHandler(BaseHTTPRequestHandler):
    """Implementa una API JSON mínima y sirve los archivos estáticos permitidos."""

    server: "ChefIAWebServer"

    def do_GET(self) -> None:  # noqa: N802
        """Atiende la vista, los archivos estáticos y las rutas de consulta."""

        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        if path == "/api/policies":
            self._send_json(HTTPStatus.OK, {"policy": self.server.runtime.policy_text})
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        """Atiende una solicitud de receta enviada desde el chat."""

        path = urlparse(self.path).path
        if path not in {"/api/options", "/api/chat"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Ruta no encontrada."})
            return

        payload = self._read_json()
        if payload is None:
            return
        ingredients = payload.get("ingredients")
        servings = payload.get("servings")
        if not isinstance(ingredients, str) or len(ingredients) > 1_000:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Los ingredientes no son válidos."})
            return
        if not isinstance(servings, (str, int)):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "El número de personas no es válido."})
            return

        try:
            if path == "/api/options":
                options = self.server.runtime.options(ingredients, str(servings))
                self._send_json(HTTPStatus.OK, {"options": [option.as_dict() for option in options]})
                return
            recipe_name = payload.get("recipe_name")
            if not isinstance(recipe_name, str):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Selecciona una receta válida."})
                return
            reply = self.server.runtime.answer(ingredients, str(servings), recipe_name)
        except (RequestValidationError, NoMatchingRecipeError, ConfigurationError) as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception:
            # No se expone la configuración ni los detalles del proveedor de IA.
            self._send_json(
                HTTPStatus.BAD_GATEWAY,
                {"error": "No fue posible obtener una respuesta del agente. Inténtalo de nuevo."},
            )
        else:
            self._send_json(HTTPStatus.OK, {"reply": reply})

    def _read_json(self) -> dict[str, Any] | None:
        """Lee un cuerpo JSON pequeño y devuelve errores claros al navegador."""

        content_length = self.headers.get("Content-Length", "")
        try:
            length = int(content_length)
        except ValueError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Solicitud inválida."})
            return None
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "Solicitud demasiado grande."})
            return None
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "El cuerpo debe ser JSON válido."})
            return None
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "El cuerpo debe ser un objeto JSON."})
            return None
        return payload

    def _serve_static(self, path: str) -> None:
        """Sirve únicamente los recursos de la vista, sin exponer código ni secretos."""

        static_files = {
            "/": self.server.static_directory / "Desafio.html",
            "/Desafio.html": self.server.static_directory / "Desafio.html",
            "/Desafio.css": self.server.static_directory / "Desafio.css",
            "/Desafio.js": self.server.static_directory / "Desafio.js",
            "/assets/ElItacate3.jpeg": self.server.data_directory / "ElItacate3.jpeg",
        }
        file_path = static_files.get(path)
        if file_path is None or not file_path.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Recurso no encontrado."})
            return
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        """Devuelve una respuesta JSON UTF-8 consistente."""

        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        """Mantiene un registro HTTP breve para diagnóstico en OCI."""

        print(f"{self.address_string()} - {format % args}")


class ChefIAWebServer(ThreadingHTTPServer):
    """Servidor con acceso al runtime del agente y a la carpeta de archivos estáticos."""

    def __init__(self, host: str, port: int, data_directory: Path) -> None:
        """Configura el servidor y carga la aplicación antes de aceptar tráfico."""

        self.data_directory = data_directory.resolve()
        self.static_directory = self.data_directory / "html"
        self.runtime = AgentRuntime(self.data_directory)
        super().__init__((host, port), ChefIARequestHandler)


def main() -> None:
    """Inicia la aplicación web con host, puerto y carpeta de datos configurables."""

    parser = argparse.ArgumentParser(description="Servidor web de Chef IA")
    parser.add_argument("--data-dir", default=str(DATA_DIRECTORY), help="Carpeta de documentos y HTML.")
    parser.add_argument("--host", default="0.0.0.0", help="Host de escucha.")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8080")), help="Puerto HTTP.")
    arguments = parser.parse_args()

    server = ChefIAWebServer(arguments.host, arguments.port, Path(arguments.data_dir))
    print(f"Chef IA disponible en http://{arguments.host}:{arguments.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
