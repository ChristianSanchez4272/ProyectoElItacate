"""Lectura de texto para documentos DOCX usando solamente la biblioteca estándar."""

from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ElementTree


WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
DOCUMENT_XML = "word/document.xml"


class DocumentReadError(RuntimeError):
    """Indica que un documento requerido no pudo leerse."""


def read_paragraphs(path: Path) -> tuple[str, ...]:
    """Devuelve los párrafos no vacíos de un DOCX en su orden original.

    Un archivo DOCX es un archivo ZIP que contiene XML. Esta función toma el XML
    principal del documento, por lo que evita depender de Word o paquetes externos.
    """

    try:
        with ZipFile(path) as document:
            xml_bytes = document.read(DOCUMENT_XML)
    except (FileNotFoundError, KeyError, BadZipFile) as error:
        raise DocumentReadError(f"No se pudo leer el documento: {path.name}") from error

    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as error:
        raise DocumentReadError(f"El XML de {path.name} no es válido.") from error

    paragraphs: list[str] = []
    for paragraph in root.iter(f"{WORD_NAMESPACE}p"):
        text = "".join(paragraph.itertext()).strip()
        if text:
            paragraphs.append(text)
    return tuple(paragraphs)
