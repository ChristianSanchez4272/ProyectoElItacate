"""Pruebas de la API HTTP sin realizar llamadas a Cohere."""

from __future__ import annotations

import json
from pathlib import Path
import threading
import unittest
from urllib.request import Request, urlopen

from chef_ia.web_server import ChefIAWebServer


DATA_DIRECTORY = Path(__file__).resolve().parents[2]


class FakeAgent:
    """Sustituye Cohere para verificar la API sin usar una clave ni red externa."""

    def answer(self, recipe: object, request: object) -> str:
        """Devuelve un texto determinista con el nombre de la receta elegida."""

        return f"Respuesta de prueba: {recipe.name}"


class WebServerTests(unittest.TestCase):
    """Comprueba las rutas públicas y el envío de una solicitud de receta."""

    @classmethod
    def setUpClass(cls) -> None:
        """Inicia un servidor efímero para todas las pruebas de esta clase."""

        cls.server = ChefIAWebServer("127.0.0.1", 0, DATA_DIRECTORY)
        cls.server.runtime._agent = FakeAgent()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        """Detiene el servidor efímero al terminar las pruebas."""

        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_health_endpoint(self) -> None:
        """El endpoint de estado permite a OCI comprobar que la aplicación vive."""

        with urlopen(f"{self.base_url}/health") as response:
            self.assertEqual(200, response.status)
            self.assertEqual({"status": "ok"}, json.load(response))

    def test_policies_endpoint(self) -> None:
        """La vista puede recuperar las políticas antes de activar el chat."""

        with urlopen(f"{self.base_url}/api/policies") as response:
            policy = json.load(response)["policy"]
        self.assertIn("Políticas de Uso", policy)

    def test_chat_endpoint(self) -> None:
        """El chat muestra opciones y devuelve la receta que la persona eligió."""

        body = json.dumps({"ingredients": "pollo, jitomate, chiles", "servings": 2}).encode()
        request = Request(
            f"{self.base_url}/api/options",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            payload = json.load(response)
        self.assertEqual("Tinga de pollo", payload["options"][0]["name"])

        recipe_body = json.dumps(
            {"ingredients": "pollo, jitomate, chiles", "servings": 2, "recipe_name": "Tinga de pollo"}
        ).encode()
        recipe_request = Request(
            f"{self.base_url}/api/chat",
            data=recipe_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(recipe_request) as response:
            payload = json.load(response)
        self.assertEqual("Respuesta de prueba: Tinga de pollo", payload["reply"])


if __name__ == "__main__":
    unittest.main()
