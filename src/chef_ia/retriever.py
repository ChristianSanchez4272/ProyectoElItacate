"""Recuperación local y explicable de documentos para el agente de LangChain."""

from __future__ import annotations

import re
import unicodedata

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class KnowledgeRetriever:
    """Fragmenta documentos una vez y recupera los más relevantes por palabras."""

    def __init__(self, documents: tuple[Document, ...]) -> None:
        """Construye un índice local, sin enviar documentos a servicios externos."""

        splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=120)
        self._chunks = tuple(splitter.split_documents(documents))

    def search(self, query: str, limit: int = 4) -> tuple[Document, ...]:
        """Devuelve hasta ``limit`` fragmentos ordenados por coincidencia de términos."""

        terms = set(_tokens(query))
        if not terms:
            return ()
        scored = [
            (len(terms & set(_tokens(chunk.page_content))), position, chunk)
            for position, chunk in enumerate(self._chunks)
        ]
        # En empates se conserva el orden de carga. Esto evita que un fragmento
        # genérico posterior desplace a uno más directamente relacionado.
        ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
        return tuple(chunk for score, _, chunk in ranked[:limit] if score)


def _tokens(text: str) -> tuple[str, ...]:
    """Normaliza texto español para una comparación local de bajo costo."""

    normalized = "".join(
        character
        for character in unicodedata.normalize("NFD", text.casefold())
        if unicodedata.category(character) != "Mn"
    )
    return tuple(re.findall(r"[a-z0-9]+", normalized))
