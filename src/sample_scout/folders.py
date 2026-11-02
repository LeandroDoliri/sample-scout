"""Árbol de carpetas de la vista Carpetas, armado con las rutas que ya están en la base (sin
recorrer el disco). Sin Qt: el modelo de la ventana (app.FolderModel) solo lo muestra."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(eq=False)
class FolderNode:
    """Una carpeta: `root` y `folder` como en la tabla `samples` ("." = la raíz misma)."""

    name: str
    root: str
    folder: str
    parent: FolderNode | None = None
    direct: int = 0  # samples directamente en esta carpeta
    total: int = 0  # los de adentro, con todas las subcarpetas
    cover: str | None = None  # portada que está en esta carpeta (la del pack)
    children: list[FolderNode] = field(default_factory=list)
    row: int = 0  # posición entre sus hermanas (para el modelo de Qt)

    @property
    def path(self) -> str:
        """Ruta absoluta (la que se guarda para recordar la carpeta abierta)."""
        return self.root if self.folder == "." else os.path.join(self.root, self.folder)

    def walk(self):
        """Esta carpeta y todas las de adentro."""
        yield self
        for child in self.children:
            yield from child.walk()


def _key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def build_tree(roots: list[str], counts: list[dict]) -> list[FolderNode]:
    """Una rama por raíz con sus subcarpetas, desde las filas de `db.folder_counts` (root,
    folder, n, cover). Aparecen también las carpetas intermedias sin samples propios. Las
    raíces sin samples quedan con 0. Todo va ordenado por nombre, sin distinguir mayúsculas.

    La portada de una fila puede estar en esa carpeta o en una de más arriba (el escaneo
    hereda la del pack): se le asigna a la carpeta donde está el archivo de imagen, así se ve
    una sola vez, en la carpeta del pack."""
    tops: dict[str, FolderNode] = {}
    for root in roots:
        tops.setdefault(root, FolderNode(os.path.basename(root.rstrip("\\/")) or root, root, "."))
    index: dict[tuple[str, str], FolderNode] = {(n.root, "."): n for n in tops.values()}
    by_path: dict[str, FolderNode] = {}
    covers: set[str] = set()

    def node_for(root: str, folder: str) -> FolderNode:
        node = index.get((root, folder))
        if node is None:
            parent_folder = os.path.dirname(folder) or "."
            parent = node_for(root, parent_folder)
            node = FolderNode(os.path.basename(folder), root, folder, parent)
            parent.children.append(node)
            index[(root, folder)] = node
        return node

    for row in counts:
        root = row["root"]
        if root not in tops:  # samples de una raíz que ya no está (no debería pasar)
            continue
        node = node_for(root, os.path.normpath(row["folder"]) if row["folder"] != "." else ".")
        node.direct += row["n"]
        if row.get("cover"):
            covers.add(row["cover"])

    for top in tops.values():
        _finish(top)
        for node in top.walk():
            by_path.setdefault(_key(node.path), node)
    for cover in covers:
        node = by_path.get(_key(os.path.dirname(cover)))
        if node is not None and node.cover is None:
            node.cover = cover
    result = sorted(tops.values(), key=lambda n: (n.name.casefold(), n.root))
    for i, node in enumerate(result):
        node.row = i
    return result


def _finish(node: FolderNode) -> int:
    """Ordena las subcarpetas, numera sus filas y suma los totales (sin recursión: hay
    librerías con anidación muy profunda)."""
    stack = [(node, False)]
    while stack:
        current, done = stack.pop()
        if done:
            current.total = current.direct + sum(c.total for c in current.children)
            continue
        current.children.sort(key=lambda n: n.name.casefold())
        for i, child in enumerate(current.children):
            child.row = i
        stack.append((current, True))
        stack.extend((child, False) for child in current.children)
    return node.total


def find(tree: list[FolderNode], path: str) -> FolderNode | None:
    """La carpeta con esa ruta absoluta (sin distinguir mayúsculas), o None."""
    key = _key(path)
    for top in tree:
        top_key = _key(top.root)
        if key != top_key and not key.startswith(top_key.rstrip("\\/") + os.sep):
            continue
        node = top
        rel = os.path.relpath(key, top_key)
        if rel == ".":
            return node
        for part in rel.split(os.sep):
            node = next((c for c in node.children if c.name.casefold() == part.casefold()),
                        None)
            if node is None:
                break
        if node is not None:
            return node
    return None
