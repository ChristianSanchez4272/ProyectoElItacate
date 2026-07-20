"""Configuración segura de variables de entorno para Cohere."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


DEFAULT_COHERE_MODEL = "command-a-plus-05-2026"


class ConfigurationError(RuntimeError):
    """Indica que falta una configuración necesaria para usar el modelo."""


@dataclass(frozen=True, slots=True)
class CohereSettings:
    """Valores necesarios para inicializar ChatCohere sin exponer secretos."""

    api_key: str
    model: str

    @classmethod
    def from_environment(cls) -> "CohereSettings":
        """Carga ``.env`` y valida que la clave de Cohere esté disponible."""

        load_dotenv()
        api_key = os.getenv("COHERE_API_KEY", "").strip()
        if not api_key:
            raise ConfigurationError(
                "Falta COHERE_API_KEY. Crea el archivo .env a partir de .env.example "
                "y agrega tu clave sin compartirla."
            )
        return cls(api_key=api_key, model=os.getenv("COHERE_MODEL", DEFAULT_COHERE_MODEL))
