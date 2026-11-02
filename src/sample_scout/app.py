"""Ventana principal: filtros, lista de samples, preescucha y arrastre al DAW."""

from __future__ import annotations

import html
import json
import multiprocessing
import os
import sqlite3
import subprocess
import sys
import traceback
from collections import OrderedDict

from PySide6.QtCore import (QAbstractTableModel, QItemSelection, QItemSelectionModel, QMimeData,
                            QModelIndex, QObject, QRegularExpression, QRunnable, QSettings, QSize,
                            Qt, QThread, QThreadPool, QTimer, QUrl, Signal)
from PySide6.QtGui import (QAction, QColor, QCursor, QDesktopServices, QGuiApplication,
                           QIcon, QImage, QImageReader, QKeySequence, QPainter, QPixmap,
                           QRegularExpressionValidator)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
                               QCompleter, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QPushButton, QSpinBox, QSplitter, QStyledItemDelegate,
                               QTableView, QToolBar, QVBoxLayout, QWidget)

from sample_scout import APP_DIR, __version__, db, scanner, updater
from sample_scout.analyzer import NOTES
from sample_scout.parser import INSTRUMENT_LABELS

# Igual que el AppUserModelID de los accesos directos del instalador: así la ventana y el
# acceso directo son la misma app en la barra de tareas
APP_USER_MODEL_ID = "LeandroDoliri.SampleScout"

COLUMNS = [
    ("favorite", "★"), ("name", "Nombre"), ("instrument", "Instrumento"), ("kind", "Tipo"),
    ("bpm", "BPM"), ("key", "Key"), ("rating", "Estrellas"), ("duration", "Duración"),
    ("wave", "Onda"), ("tags", "Tags"), ("folder", "Carpeta"),
]
COLUMN_WIDTHS = (28, 320, 100, 80, 60, 60, 80, 80, 90, 140, 200)
FAVORITE_COLUMN = 0
NAME_COLUMN = 1
RATING_COLUMN = 6
NUMERIC_FIELDS = ("favorite", "bpm", "rating", "duration")
UNSORTABLE_FIELDS = ("wave",)
DEFAULT_HIDDEN = ("wave",)  # columnas opcionales: arrancan ocultas
KIND_LABELS = {"loop": "Loop", "oneshot": "One-shot"}
# En el menú de columnas, "★" u "Onda" solos no se entienden.
COLUMN_MENU_LABELS = {"favorite": "Favorito", "wave": "Forma de onda (mini)"}
STAR_COLOR = QColor("#d4a017")
WAVE_COLOR = QColor("#9ca3af")
WAVE_PLAYED_COLOR = QColor("#0f766e")
GROUP_SHADE = QColor(15, 118, 110, 22)  # fondo de un grupo sí y otro no en "Duplicados"
PEAKS_ROLE = Qt.UserRole + 1


def stars(rating: int) -> str:
    return "★" * rating + "☆" * (5 - rating)


def paint_peaks(painter: QPainter, rect, peaks: bytes, color: QColor,
                played_color: QColor | None = None, progress: float | None = None) -> None:
    """Dibuja la forma de onda (simétrica, una línea por píxel) dentro de `rect`. Con
    `progress` (0 a 1) lo ya reproducido va en `played_color`."""
    width, height = rect.width(), rect.height()
    if not peaks or width <= 0 or height <= 0:
        return
    middle = rect.top() + height / 2
    n = len(peaks)
    played_x = rect.left() + progress * width if progress is not None else None
    painter.save()
    for x in range(width):
        lo = x * n // width
        hi = max(lo + 1, (x + 1) * n // width)
        half = max(0.5, max(peaks[lo:hi]) / 255 * (height / 2 - 1))
        px = rect.left() + x
        played = played_x is not None and px <= played_x
        painter.setPen(played_color if played and played_color else color)
        painter.drawLine(px, int(middle - half), px, int(middle + half))
    painter.restore()


class WaveformView(QWidget):
    """Forma de onda grande del panel de detalle, con el cursor de reproducción. Un clic emite
    `seek` con la posición (0 a 1) para reproducir desde ahí."""

    seek = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.peaks = b""
        self.text = ""
        self.progress: float | None = None
        self.setFixedHeight(64)

    def set_peaks(self, peaks: bytes | None, text: str = "") -> None:
        self.peaks = peaks or b""
        self.text = "" if self.peaks else text
        self.setCursor(Qt.PointingHandCursor if self.peaks else Qt.ArrowCursor)
        self.setToolTip("Clic para reproducir desde ese punto" if self.peaks else "")
        self.update()

    def set_progress(self, progress: float | None) -> None:
        if progress != self.progress:
            self.progress = progress
            self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setPen(QColor("#e5e7eb"))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if not self.peaks:
            painter.setPen(WAVE_COLOR)
            painter.drawText(self.rect(), Qt.AlignCenter, self.text)
            return
        rect = self.rect().adjusted(1, 3, -1, -3)
        paint_peaks(painter, rect, self.peaks, WAVE_COLOR, WAVE_PLAYED_COLOR, self.progress)
        if self.progress is not None:
            x = int(rect.left() + self.progress * rect.width())
            painter.setPen(QColor("#111827"))
            painter.drawLine(x, 0, x, self.height())

    def mousePressEvent(self, event) -> None:
        if self.peaks and event.button() == Qt.LeftButton and self.width() > 0:
            self.seek.emit(min(1.0, max(0.0, event.position().x() / self.width())))


class WaveDelegate(QStyledItemDelegate):
    """Mini forma de onda de la columna opcional "Onda"."""

    def paint(self, painter, option, index) -> None:
        super().paint(painter, option, index)  # fondo y selección
        peaks = index.data(PEAKS_ROLE)
        if peaks:
            paint_peaks(painter, option.rect.adjusted(3, 3, -3, -3), peaks, WAVE_COLOR)


class _WaveJob(QRunnable):
    """Calcula la forma de onda de un sample que todavía no la tiene (el análisis no llegó a
    ese archivo), fuera del hilo de la ventana."""

    def __init__(self, path: str, done: Signal) -> None:
        super().__init__()
        self.path = path
        self.done = done

    def run(self) -> None:
        from sample_scout.analyzer import waveform_peaks

        try:
            peaks = waveform_peaks(self.path)
        except Exception:
            peaks = b""
        self.done.emit(self.path, peaks)


class _CoverJob(QRunnable):
    """Lee y achica una portada fuera del hilo de la ventana (QImage sí se puede usar en otro
    hilo; QPixmap no)."""

    def __init__(self, path: str, done: Signal) -> None:
        super().__init__()
        self.path = path
        self.done = done

    def run(self) -> None:
        reader = QImageReader(self.path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and max(size.width(), size.height()) > CoverCache.BIG:
            reader.setScaledSize(size.scaled(CoverCache.BIG, CoverCache.BIG, Qt.KeepAspectRatio))
        image = reader.read()
        thumb = (image.scaled(CoverCache.THUMB, CoverCache.THUMB, Qt.KeepAspectRatio,
                              Qt.SmoothTransformation) if not image.isNull() else image)
        self.done.emit(self.path, image, thumb)


class CoverCache(QObject):
    """Portadas ya escaladas, por ruta. `thumb()` y `big()` devuelven lo que haya en cache y,
    si falta, piden la carga en segundo plano y avisan con `loaded(ruta)` cuando llega."""

    THUMB = 20
    BIG = 240
    MAX_BIG = 64  # las grandes ocupan ~200 KB cada una
    loaded = Signal(str)
    _done = Signal(str, QImage, QImage)

    def __init__(self) -> None:
        super().__init__()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._thumbs: dict[str, QPixmap] = {}
        self._bigs: OrderedDict[str, QPixmap] = OrderedDict()
        self._pending: set[str] = set()
        self._done.connect(self._on_done)

    def thumb(self, path: str) -> QPixmap | None:
        pixmap = self._thumbs.get(path)
        if pixmap is None:
            self._request(path)
        return pixmap if pixmap is not None and not pixmap.isNull() else None

    def big(self, path: str) -> QPixmap | None:
        pixmap = self._bigs.get(path)
        if pixmap is None:
            self._request(path, force=True)
            return None
        self._bigs.move_to_end(path)
        return pixmap if not pixmap.isNull() else None

    def _request(self, path: str, force: bool = False) -> None:
        # Una portada ya leída (aunque haya fallado) no se vuelve a pedir para la miniatura.
        if path in self._pending or (path in self._thumbs and not force):
            return
        self._pending.add(path)
        self.pool.start(_CoverJob(path, self._done))

    def _on_done(self, path: str, image: QImage, thumb: QImage) -> None:
        self._pending.discard(path)
        self._thumbs[path] = QPixmap.fromImage(thumb)
        self._bigs[path] = QPixmap.fromImage(image)
        while len(self._bigs) > self.MAX_BIG:
            self._bigs.popitem(last=False)
        self.loaded.emit(path)


class SampleModel(QAbstractTableModel):
    """Tabla de samples: cada fila es un dict de `db.search`. Ordena en memoria (los vacíos
    siempre al final, y conserva el orden elegido al recargar) y entrega rutas de archivo al
    arrastrar."""

    def __init__(self, covers: CoverCache) -> None:
        super().__init__()
        self.rows: list[dict] = []
        self.sort_by: tuple[int, Qt.SortOrder] | None = None  # None = orden de la consulta
        self._row_of: dict[str, int] = {}
        self.covers = covers
        covers.loaded.connect(self._on_cover_loaded)
        self._blank: QPixmap | None = None  # mismo tamaño que una miniatura, para alinear
        self.grouped = False  # vista "Duplicados": sombrea un grupo de copias sí y otro no
        self._shaded: set[int] = set()

    def _on_cover_loaded(self, _path: str) -> None:
        if self.rows:
            column = NAME_COLUMN
            self.dataChanged.emit(self.index(0, column), self.index(len(self.rows) - 1, column),
                                  [Qt.DecorationRole])

    def _thumbnail(self, row: dict) -> QPixmap:
        pixmap = self.covers.thumb(row["cover"]) if row["cover"] else None
        if pixmap is None:
            if self._blank is None:
                self._blank = QPixmap(CoverCache.THUMB, CoverCache.THUMB)
                self._blank.fill(Qt.transparent)
            pixmap = self._blank
        return pixmap

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = self._sorted(rows)
        self._reindex()
        self.endResetModel()

    def update_rows(self, rows_by_path: dict[str, dict]) -> None:
        """Reemplaza filas ya mostradas (después de marcar favoritos o estrellas) sin recargar
        ni reordenar la tabla."""
        for path, row in rows_by_path.items():
            i = self._row_of.get(path)
            if i is not None:
                self.rows[i] = row
                self.dataChanged.emit(self.index(i, 0), self.index(i, len(COLUMNS) - 1))

    def row_of(self, path: str) -> int | None:
        return self._row_of.get(path)

    def _reindex(self) -> None:
        self._row_of = {r["path"]: i for i, r in enumerate(self.rows)}
        self._shaded = set()
        if self.grouped:
            shade, last = True, object()
            for i, r in enumerate(self.rows):
                if r["content_hash"] != last:
                    shade, last = not shade, r["content_hash"]
                if shade:
                    self._shaded.add(i)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section][1]
        return None

    def data(self, index, role=Qt.DisplayRole):
        row = self.rows[index.row()]
        field = COLUMNS[index.column()][0]
        value = row[field]
        if role == Qt.DecorationRole and field == "name":
            return self._thumbnail(row)
        if role == Qt.BackgroundRole and index.row() in self._shaded:
            return GROUP_SHADE
        if field == "wave":
            return row["peaks"] if role == PEAKS_ROLE else None
        if field in ("favorite", "rating"):
            if role == Qt.DisplayRole:
                if field == "favorite":
                    return "★" if value else "☆"
                return stars(value) if value else ""
            if role == Qt.ForegroundRole and value:
                return STAR_COLOR
            if role == Qt.ForegroundRole:
                return QColor("#9ca3af")
            if role == Qt.TextAlignmentRole and field == "favorite":
                return int(Qt.AlignCenter)
            if role != Qt.ToolTipRole:
                return None
        if role == Qt.DisplayRole:
            if value is None:
                return "…" if not row["analyzed"] and field in ("bpm", "key", "duration") else ""
            if field == "instrument":
                return INSTRUMENT_LABELS.get(value, value)
            if field == "kind":
                return KIND_LABELS.get(value, value)
            if field == "duration":
                return f"{value:.2f} s"
            if field == "bpm":
                return f"{value:g}"
            return value
        if role == Qt.ToolTipRole:
            sources = [f"{f}: {row[f + '_source']}" for f in ("bpm", "key", "instrument", "kind")
                       if row[f + "_source"]]
            tip = row["path"]
            if sources:
                tip += "\nFuente → " + ", ".join(sources)
            if row["tags"]:
                tip += f"\nTags: {row['tags']}"
            if row["copies"] > 1:
                tip += f"\nDuplicado: {row['copies']} copias en la librería"
            if row["error"]:
                tip += f"\nError: {row['error']}"
            return tip
        if role == Qt.TextAlignmentRole and field in ("bpm", "duration"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def sort(self, column, order=Qt.AscendingOrder) -> None:
        # column -1: sin orden (el historial se muestra en orden de escucha)
        self.sort_by = (column, order) if column >= 0 else None
        if self.sort_by:
            self.beginResetModel()
            self.rows = self._sorted(self.rows)
            self._reindex()
            self.endResetModel()

    def _sorted(self, rows: list[dict]) -> list[dict]:
        if not self.sort_by:
            return rows
        column, order = self.sort_by
        field = COLUMNS[column][0]
        if field in UNSORTABLE_FIELDS:
            return rows
        numeric = field in NUMERIC_FIELDS
        filled = [r for r in rows if r[field] is not None]
        empty = [r for r in rows if r[field] is None]  # siempre al final
        filled.sort(key=lambda r: r[field] if numeric else str(r[field]).lower(),
                    reverse=order == Qt.DescendingOrder)
        return filled + empty

    # --- Arrastre: el DAW recibe una lista de archivos, igual que desde el Explorador ---
    def flags(self, index):
        return super().flags(index) | Qt.ItemIsDragEnabled

    def mimeTypes(self) -> list[str]:
        return ["text/uri-list"]

    def mimeData(self, indexes) -> QMimeData:
        paths = sorted({self.rows[i.row()]["path"] for i in indexes})
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        return mime

    def supportedDragActions(self):
        return Qt.CopyAction


class ViewList(QListWidget):
    """Panel "Biblioteca": toda la librería, el historial y las colecciones. Cada ítem guarda
    (tipo, id) en UserRole. Acepta filas arrastradas desde la tabla sobre una colección."""

    dropped = Signal(int, list)  # id de la colección, rutas

    def __init__(self, source: QWidget) -> None:
        super().__init__()
        self.source = source
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def _target(self, event) -> int | None:
        if event.source() is not self.source or not event.mimeData().hasUrls():
            return None
        item = self.itemAt(event.position().toPoint())
        view = item.data(Qt.UserRole) if item else None
        return view[1] if view and view[0] == "collection" else None

    def dragEnterEvent(self, event) -> None:
        if event.source() is self.source and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._target(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        collection = self._target(event)
        if collection is None:
            event.ignore()
            return
        paths = [os.path.normpath(u.toLocalFile()) for u in event.mimeData().urls()]
        event.acceptProposedAction()
        self.dropped.emit(collection, paths)


class EditDialog(QDialog):
    """Corrige tipo, instrumento, BPM y key de uno o varios samples, y les agrega o quita tags.
    Cada campo arranca con el valor que comparten todos (o "(varios)"); solo se guarda lo que el
    usuario cambió. `changes()` devuelve ({campo: valor}, tags a agregar, tags a quitar)."""

    MIXED = "__mixed__"

    def __init__(self, parent: QWidget, rows: list[dict], known_tags: list[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Editar datos" if len(rows) == 1 else f"Editar {len(rows)} samples")
        self.setMinimumWidth(380)
        self.rows = rows

        def common(field):
            values = {r[field] for r in rows}
            return values.pop() if len(values) == 1 else self.MIXED

        def combo(field, options):
            box = QComboBox()
            value = common(field)
            if value == self.MIXED:
                box.addItem("(varios)", self.MIXED)
            box.addItem("—", None)
            for label, data in options:
                box.addItem(label, data)
            box.setCurrentIndex(max(0, box.findData(value)))
            return box

        self.kind = combo("kind", [(v, k) for k, v in KIND_LABELS.items()])
        self.instrument = combo("instrument", sorted(
            ((v, k) for k, v in INSTRUMENT_LABELS.items()), key=lambda e: e[0]))
        self.key = combo("key", [(n + m, n + m) for n in NOTES for m in ("", "m")])
        bpm = common("bpm")
        self.bpm = QLineEdit("" if bpm in (None, self.MIXED) else f"{bpm:g}")
        self.bpm.setPlaceholderText("(varios)" if bpm == self.MIXED else "—")
        self.bpm.setValidator(QRegularExpressionValidator(
            QRegularExpression(r"\d{0,3}([.,]\d{0,2})?"), self.bpm))
        self.initial = {"kind": self.kind.currentIndex(),
                        "instrument": self.instrument.currentIndex(),
                        "key": self.key.currentIndex(), "bpm": self.bpm.text()}

        # Tags: tildado = lo tienen todos; a medias = solo algunos.
        sample_tags = [set((r["tags"] or "").split(", ")) - {""} for r in rows]
        self.tags = QListWidget()
        self.tags.setMaximumHeight(110)
        for tag in sorted(set().union(*sample_tags), key=str.lower):
            item = QListWidgetItem(tag)
            n = sum(tag in t for t in sample_tags)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if n == len(rows):
                item.setCheckState(Qt.Checked)
            else:
                item.setFlags(item.flags() | Qt.ItemIsUserTristate)
                item.setCheckState(Qt.PartiallyChecked)
            self.tags.addItem(item)
        self.tags_initial = [self.tags.item(i).checkState() for i in range(self.tags.count())]
        self.new_tags = QLineEdit(placeholderText="Separados por coma: oscuro, techno…")
        completer = QCompleter(known_tags, self.new_tags)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.new_tags.setCompleter(completer)

        form = QFormLayout()
        form.addRow("Tipo", self.kind)
        form.addRow("Instrumento", self.instrument)
        form.addRow("BPM", self.bpm)
        form.addRow("Key", self.key)
        if self.tags.count():
            form.addRow("Tags", self.tags)
        form.addRow("Agregar tags", self.new_tags)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Lo que corregís acá queda con fuente <i>user</i>: re-escanear "
                                "o re-analizar no lo pisa. Dejá el BPM vacío o elegí — para "
                                "dejar un dato vacío.", wordWrap=True))
        layout.addWidget(buttons)

    def accept(self) -> None:
        text = self.bpm.text().strip().replace(",", ".")
        if text and text != self.initial["bpm"] and not 20 <= float(text) <= 400:
            QMessageBox.warning(self, "BPM fuera de rango", "El BPM tiene que estar entre 20 "
                                "y 400 (o vacío).")
            return
        super().accept()

    def changes(self) -> tuple[dict, list[str], list[str]]:
        fields = {}
        for field, box in (("kind", self.kind), ("instrument", self.instrument),
                           ("key", self.key)):
            if box.currentIndex() != self.initial[field] and box.currentData() != self.MIXED:
                fields[field] = box.currentData()
        text = self.bpm.text().strip().replace(",", ".")
        if text != self.initial["bpm"]:
            fields["bpm"] = float(text) if text else None
        add = [t.strip() for t in self.new_tags.text().split(",") if t.strip()]
        remove = []
        for i in range(self.tags.count()):
            item = self.tags.item(i)
            if item.checkState() == self.tags_initial[i]:
                continue
            if item.checkState() == Qt.Checked:
                add.append(item.text())
            elif item.checkState() == Qt.Unchecked:
                remove.append(item.text())
        return fields, add, remove


class LibraryWorker(QObject):
    """Escanea y analiza en segundo plano para no congelar la ventana."""

    progress = Signal(str)
    indexed = Signal()
    finished = Signal()

    def __init__(self, roots: list[str]) -> None:
        super().__init__()
        self.roots = roots
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        conn = db.connect()
        try:
            for root in self.roots:
                self.progress.emit(f"Indexando {root}…")
                scanner.scan_root(conn, root, self.progress.emit, lambda: self._stop)
            self.indexed.emit()
            if not self._stop:
                scanner.analyze_pending(conn, self.progress.emit, lambda: self._stop)
        finally:
            conn.close()
            self.finished.emit()


class TaskWorker(QObject):
    """Corre una función en otro hilo. La función recibe `progress.emit` para informar avances."""

    progress = Signal(str)
    done = Signal(object)
    failed = Signal(object)

    def __init__(self, fn) -> None:
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self.fn(self.progress.emit))
        except Exception as exc:
            self.failed.emit(exc)


class MainWindow(QMainWindow):
    """Ventana principal. Al abrir: muestra la librería, re-escanea las carpetas (solo procesa lo
    nuevo o modificado) y consulta en segundo plano si hay una versión nueva."""

    _wave_done = Signal(str, object)  # ruta, picos (de _WaveJob)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Sample Scout {__version__}")
        self.resize(1400, 820)
        self.conn = db.connect()
        self.thread: QThread | None = None
        self.worker: LibraryWorker | None = None
        self.tasks: list[tuple[QThread, TaskWorker]] = []  # referencias vivas mientras corren
        self.update_info: dict = {}
        self._restoring = False  # refresh() restaurando la selección: no reproducir
        self.covers = CoverCache()
        self.covers.loaded.connect(self._on_cover_loaded)
        self.wave_pool = QThreadPool(self)
        self.wave_pool.setMaxThreadCount(1)
        self._wave_pending: set[str] = set()
        self._wave_done.connect(self._on_wave_done)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self._pending_seek: float | None = None  # posición a aplicar cuando cargue el archivo
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.playbackStateChanged.connect(self._on_playback_state)
        self.playhead_timer = QTimer(self, interval=40)
        self.playhead_timer.timeout.connect(self._update_playhead)

        self._build_ui()
        self.search_timer = QTimer(self, singleShot=True, interval=200)
        self.search_timer.timeout.connect(self.refresh)
        self.refresh()
        if db.list_roots(self.conn):
            self.start_scan()
        self.run_task(lambda _log: updater.check(), self._on_update_checked)

    def run_task(self, fn, on_done, on_failed=None) -> None:
        """Corre fn(log) en un hilo aparte. on_done / on_failed se llaman en el hilo de la
        ventana con el resultado o la excepción; los mensajes de log van a la barra de estado."""
        thread = QThread(self)
        worker = TaskWorker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.statusBar().showMessage)
        worker.done.connect(on_done)
        worker.failed.connect(on_failed or (lambda exc: None))
        entry = (thread, worker)

        def cleanup(*_args):
            thread.quit()
            thread.wait()
            self.tasks.remove(entry)

        worker.done.connect(cleanup)
        worker.failed.connect(cleanup)
        self.tasks.append(entry)
        thread.start()

    # --- UI ---
    def _build_ui(self) -> None:
        toolbar = QToolBar("Principal", movable=False)
        self.addToolBar(toolbar)
        add_action = QAction("Agregar carpeta…", self)
        add_action.triggered.connect(self.add_folder)
        toolbar.addAction(add_action)
        rescan_action = QAction("Re-escanear", self)
        rescan_action.triggered.connect(self.start_scan)
        toolbar.addAction(rescan_action)
        toolbar.addSeparator()
        self.search = QLineEdit(placeholderText="Buscar (nombre, carpeta, pack, tags…)",
                                clearButtonEnabled=True)
        self.search.setMaximumWidth(420)
        self.search.textChanged.connect(self._schedule_refresh)
        toolbar.addWidget(self.search)

        # Tabla central (va primero: la lista de colecciones necesita saber de dónde vienen
        # las filas que se le arrastran).
        self.model = SampleModel(self.covers)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSortIndicator(1, Qt.AscendingOrder)  # por nombre
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        self.table.setDefaultDropAction(Qt.CopyAction)
        self.table.setIconSize(QSize(CoverCache.THUMB, CoverCache.THUMB))
        self.table.setItemDelegateForColumn(COLUMNS.index(("wave", "Onda")),
                                            WaveDelegate(self.table))
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(22)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setSectionsMovable(True)  # reordenar arrastrando los encabezados
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        for col, width in enumerate(COLUMN_WIDTHS):
            self.table.setColumnWidth(col, width)
        self._restore_columns()
        self.table.selectionModel().currentRowChanged.connect(self._on_current_changed)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.clicked.connect(self._on_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        def shortcut(text, key, slot):
            action = QAction(text, self, shortcut=QKeySequence(key))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(slot)
            self.table.addAction(action)
            return action

        shortcut("Reproducir / detener", Qt.Key_Space, self.toggle_play)
        self.favorite_action = shortcut("Favorito", Qt.Key_F, self.toggle_favorite)
        self.edit_action = shortcut("Editar datos y tags…", Qt.Key_F2, self.edit_selected)
        self.remove_from_collection_action = shortcut(
            "Quitar de esta colección", Qt.Key_Delete, self.remove_selected_from_collection)
        self.rating_actions = []
        for n in range(6):
            self.rating_actions.append(shortcut(
                stars(n) if n else "Sin estrellas", Qt.Key_0 + n,
                lambda _checked=False, n=n: self.set_rating(n)))

        # Panel izquierdo: biblioteca (historial y colecciones), categorías y filtros.
        self.views = ViewList(self.table)
        self.views.setMaximumHeight(170)
        self.views.currentItemChanged.connect(self._on_view_changed)
        self.views.dropped.connect(self._on_dropped_to_collection)
        self.views.setContextMenuPolicy(Qt.CustomContextMenu)
        self.views.customContextMenuRequested.connect(self._views_menu)
        new_collection = QPushButton("Nueva colección…")
        new_collection.clicked.connect(self.new_collection)

        self.instruments = QListWidget()
        self.instruments.currentItemChanged.connect(self._schedule_refresh)
        self.kind = QComboBox()
        for label, value in (("Todos", None), ("Loops", "loop"), ("One-shots", "oneshot")):
            self.kind.addItem(label, value)
        self.kind.currentIndexChanged.connect(self._schedule_refresh)
        self.bpm_min = QSpinBox(minimum=0, maximum=300, specialValueText="—")
        self.bpm_max = QSpinBox(minimum=0, maximum=300, specialValueText="—")
        for spin in (self.bpm_min, self.bpm_max):
            spin.valueChanged.connect(self._schedule_refresh)
        self.duration_min = QDoubleSpinBox(minimum=0, maximum=600, decimals=1, singleStep=0.5,
                                           suffix=" s", specialValueText="—")
        self.duration_max = QDoubleSpinBox(minimum=0, maximum=600, decimals=1, singleStep=0.5,
                                           suffix=" s", specialValueText="—")
        for spin in (self.duration_min, self.duration_max):
            spin.valueChanged.connect(self._schedule_refresh)
        self.key = QComboBox()
        self.key.addItem("Todas", None)
        for note in NOTES:
            self.key.addItem(note, note)
            self.key.addItem(note + "m", note + "m")
        self.key.currentIndexChanged.connect(self._schedule_refresh)
        self.min_rating = QComboBox()
        self.min_rating.addItem("Todas", 0)
        for n in range(1, 6):
            self.min_rating.addItem(stars(n) + (" o más" if n < 5 else ""), n)
        self.min_rating.currentIndexChanged.connect(self._schedule_refresh)
        self.tag = QComboBox()
        self.tag.addItem("Todos", None)
        self.tag.currentIndexChanged.connect(self._schedule_refresh)
        self.favorites_only = QCheckBox("Solo favoritos")
        self.favorites_only.toggled.connect(self._schedule_refresh)
        self.hide_duplicates = QCheckBox("Ocultar duplicados")
        self.hide_duplicates.setToolTip("Muestra un solo archivo de cada grupo de copias")
        self.hide_duplicates.toggled.connect(self._schedule_refresh)
        self.autoplay = QCheckBox("Escuchar al seleccionar", checked=True)

        filters = QFormLayout()
        filters.addRow("Tipo", self.kind)
        bpm_row = QHBoxLayout()
        bpm_row.addWidget(self.bpm_min)
        bpm_row.addWidget(QLabel("a"))
        bpm_row.addWidget(self.bpm_max)
        filters.addRow("BPM", bpm_row)
        duration_row = QHBoxLayout()
        duration_row.addWidget(self.duration_min)
        duration_row.addWidget(QLabel("a"))
        duration_row.addWidget(self.duration_max)
        filters.addRow("Duración", duration_row)
        filters.addRow("Key", self.key)
        filters.addRow("Estrellas", self.min_rating)
        filters.addRow("Tag", self.tag)
        filters.addRow("", self.favorites_only)
        filters.addRow("", self.hide_duplicates)

        self.roots = QListWidget()
        self.roots.setMaximumHeight(120)
        remove_root = QPushButton("Quitar carpeta")
        remove_root.clicked.connect(self.remove_folder)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("<b>Biblioteca</b>"))
        left_layout.addWidget(self.views)
        left_layout.addWidget(new_collection)
        left_layout.addWidget(QLabel("<b>Instrumento</b>"))
        left_layout.addWidget(self.instruments, 1)
        left_layout.addLayout(filters)
        left_layout.addWidget(self.autoplay)
        left_layout.addWidget(QLabel("<b>Carpetas</b>"))
        left_layout.addWidget(self.roots)
        left_layout.addWidget(remove_root)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.table)

        # Panel de detalle: portada del pack y datos del sample actual.
        self.detail_cover = QLabel(alignment=Qt.AlignCenter)
        self.detail_cover.setFixedSize(CoverCache.BIG, CoverCache.BIG)
        self.detail_cover.setStyleSheet("QLabel { color: #9ca3af; border: 1px solid #e5e7eb; }")
        self.detail_wave = WaveformView()
        self.detail_wave.seek.connect(self._on_wave_seek)
        self.detail_info = QLabel(wordWrap=True, alignment=Qt.AlignTop | Qt.AlignLeft)
        self.detail_info.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.detail_info.linkActivated.connect(self._on_detail_link)
        self._detail_links: list[str] = []  # copias que se listan en el detalle
        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.addWidget(self.detail_cover, 0, Qt.AlignHCenter)
        detail_layout.addWidget(self.detail_wave)
        detail_layout.addWidget(self.detail_info, 1)
        detail.setMinimumWidth(CoverCache.BIG + 20)
        splitter.addWidget(detail)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([270, 1130, CoverCache.BIG + 30])
        self._update_detail()

        # Aviso de versión nueva (oculto hasta que el chequeo encuentre una)
        self.banner = QFrame(objectName="updateBanner")
        self.banner.setStyleSheet(
            "#updateBanner { background: #0f766e; } #updateBanner QLabel { color: white; }")
        banner_layout = QHBoxLayout(self.banner)
        banner_layout.setContentsMargins(12, 6, 12, 6)
        self.banner_text = QLabel()
        self.banner_update = QPushButton("Actualizar")
        self.banner_update.clicked.connect(self.apply_update)
        banner_notes = QPushButton("Ver novedades")
        banner_notes.clicked.connect(self.open_release_page)
        banner_close = QPushButton("Más tarde")
        banner_close.clicked.connect(self.banner.hide)
        banner_layout.addWidget(self.banner_text, 1)
        for button in (self.banner_update, banner_notes, banner_close):
            banner_layout.addWidget(button)
        self.banner.hide()

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.banner)
        central_layout.addWidget(splitter, 1)
        self.setCentralWidget(central)
        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)

    def _schedule_refresh(self, *_args) -> None:
        self.search_timer.start()

    # --- Datos ---
    def current_view(self) -> tuple[str, int | None]:
        """("all", None), ("history", None), ("duplicates", None) o ("collection", id)."""
        item = self.views.currentItem()
        return item.data(Qt.UserRole) if item else ("all", None)

    def refresh(self) -> None:
        """Vuelve a consultar la base con los filtros actuales y actualiza tabla, panel y estado.
        Conserva la selección y la posición de la lista (sin volver a reproducir)."""
        self._refresh_sidebar()
        item = self.instruments.currentItem()
        view, view_id = self.current_view()
        rows = db.search(
            self.conn,
            text=self.search.text(),
            instrument=item.data(Qt.UserRole) if item else None,
            kind=self.kind.currentData(),
            bpm_min=self.bpm_min.value() or None,
            bpm_max=self.bpm_max.value() or None,
            key=self.key.currentData(),
            favorites=self.favorites_only.isChecked(),
            min_rating=self.min_rating.currentData() or 0,
            tag=self.tag.currentData(),
            collection=view_id if view == "collection" else None,
            history=view == "history",
            duration_min=self.duration_min.value() or None,
            duration_max=self.duration_max.value() or None,
            duplicates=view == "duplicates",
            hide_duplicates=self.hide_duplicates.isChecked() and view != "duplicates",
        )
        selected = self.selected_paths()
        current = self.table.currentIndex()
        current_path = self.model.rows[current.row()]["path"] if current.isValid() else None
        scroll = self.table.verticalScrollBar().value()
        self._restoring = True
        try:
            self.model.grouped = view == "duplicates"
            self.model.set_rows(rows)
            self._select_paths(selected, current_path)
            self.table.verticalScrollBar().setValue(scroll)
        finally:
            self._restoring = False
        total, pending = db.stats(self.conn)
        busy = " — trabajando…" if self.thread else ""
        self.status.setText(f"{len(rows)} de {total} samples · {pending} sin analizar{busy}")
        self._update_detail()

    def _current_row(self) -> dict | None:
        index = self.table.currentIndex()
        return self.model.rows[index.row()] if index.isValid() else None

    def _update_detail(self) -> None:
        """Muestra la portada y los datos del sample actual en el panel de la derecha."""
        row = self._current_row()
        pixmap = self.covers.big(row["cover"]) if row and row["cover"] else None
        if pixmap:
            self.detail_cover.setPixmap(pixmap)
        else:
            self.detail_cover.clear()
            self.detail_cover.setText("Sin portada" if row and not row["cover"] else "")
        self._detail_links = []
        if not row:
            self.detail_wave.set_peaks(None)
            self.detail_info.setText("")
            self._update_playhead()
            return
        if row["peaks"] is None:
            self.detail_wave.set_peaks(None, "Calculando la forma de onda…")
            self._request_wave(row["path"])
        else:
            self.detail_wave.set_peaks(row["peaks"], "Sin forma de onda")
        self._update_playhead()
        bpm = f"{row['bpm']:g} BPM" if row["bpm"] else None
        duration = f"{row['duration']:.2f} s" if row["duration"] else None
        facts = [INSTRUMENT_LABELS.get(row["instrument"], row["instrument"]),
                 KIND_LABELS.get(row["kind"], row["kind"]), bpm, row["key"], duration]
        lines = [f"<b>{html.escape(row['name'])}</b>",
                 html.escape(" · ".join(f for f in facts if f))]
        if row["rating"]:
            lines.append(f"<span style='color:{STAR_COLOR.name()}'>{stars(row['rating'])}</span>")
        if row["favorite"]:
            lines.append("★ Favorito")
        if row["tags"]:
            lines.append("Tags: " + html.escape(row["tags"]))
        lines.append(f"<span style='color:#6b7280'>{html.escape(row['folder'])}</span>")
        if row["copies"] > 1:
            self._detail_links = db.copies_of(self.conn, row["path"])
            lines.append(f"<br><b>Duplicado</b> ({row['copies']} copias). También está en:")
            for i, path in enumerate(self._detail_links):
                lines.append(f"<a href='copy:{i}'>{html.escape(path)}</a>")
        self.detail_info.setText("<br>".join(lines))

    def _on_detail_link(self, link: str) -> None:
        if link.startswith("copy:"):
            i = int(link[5:])
            if i < len(self._detail_links):
                self.go_to(self._detail_links[i])

    def go_to(self, path: str) -> None:
        """Selecciona ese sample en la lista. Si los filtros lo ocultan, pasa a la vista
        "Duplicados" sin filtros (ahí están todas las copias)."""
        if self.model.row_of(path) is None:
            self._clear_filters()
            for i in range(self.views.count()):
                if self.views.item(i).data(Qt.UserRole) == ("duplicates", None):
                    self.views.blockSignals(True)
                    self.views.setCurrentRow(i)
                    self.views.blockSignals(False)
            self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
            self.refresh()
            self.search_timer.stop()
        row = self.model.row_of(path)
        if row is None:
            self.statusBar().showMessage("Ese archivo ya no está en la librería.", 4000)
            return
        index = self.model.index(row, NAME_COLUMN)
        self.table.setCurrentIndex(index)  # selecciona y, si corresponde, reproduce
        self.table.scrollTo(index, QAbstractItemView.PositionAtCenter)
        self.table.setFocus()

    def _clear_filters(self) -> None:
        for widget in (self.search, self.instruments, self.kind, self.bpm_min, self.bpm_max,
                       self.duration_min, self.duration_max, self.key, self.min_rating,
                       self.tag, self.favorites_only, self.hide_duplicates):
            widget.blockSignals(True)
        self.search.clear()
        self.instruments.setCurrentRow(0)
        for combo in (self.kind, self.key, self.min_rating, self.tag):
            combo.setCurrentIndex(0)
        for spin in (self.bpm_min, self.bpm_max, self.duration_min, self.duration_max):
            spin.setValue(0)
        self.favorites_only.setChecked(False)
        self.hide_duplicates.setChecked(False)
        for widget in (self.search, self.instruments, self.kind, self.bpm_min, self.bpm_max,
                       self.duration_min, self.duration_max, self.key, self.min_rating,
                       self.tag, self.favorites_only, self.hide_duplicates):
            widget.blockSignals(False)

    # --- Forma de onda ---
    def _request_wave(self, path: str) -> None:
        if path not in self._wave_pending:
            self._wave_pending.add(path)
            self.wave_pool.start(_WaveJob(path, self._wave_done))

    def _on_wave_done(self, path: str, peaks: bytes) -> None:
        self._wave_pending.discard(path)
        db.set_peaks(self.conn, path, peaks)
        self.model.update_rows(db.get_samples(self.conn, [path]))
        row = self._current_row()
        if row and row["path"] == path:
            self._update_detail()

    def _playing_current(self) -> bool:
        """Si el reproductor tiene cargado el sample actual de la lista."""
        row = self._current_row()
        source = self.player.source().toLocalFile()
        return bool(row and source and os.path.normcase(os.path.normpath(source))
                    == os.path.normcase(row["path"]))

    def _update_playhead(self) -> None:
        duration = self.player.duration()
        if (self._playing_current() and duration > 0
                and self.player.playbackState() != QMediaPlayer.StoppedState):
            self.detail_wave.set_progress(min(1.0, self.player.position() / duration))
        else:
            self.detail_wave.set_progress(None)

    def _on_playback_state(self, state) -> None:
        if state == QMediaPlayer.PlayingState:
            self.playhead_timer.start()
        else:
            self.playhead_timer.stop()
        self._update_playhead()

    def _on_wave_seek(self, fraction: float) -> None:
        """Clic sobre la onda: salta a ese punto (o empieza a reproducir desde ahí)."""
        index = self.table.currentIndex()
        if not index.isValid():
            return
        if (self._playing_current() and self.player.duration() > 0
                and self.player.playbackState() == QMediaPlayer.PlayingState):
            self.player.setPosition(int(fraction * self.player.duration()))
        else:
            self.play(index.row(), start=fraction)

    def _on_media_status(self, status) -> None:
        if self._pending_seek is None:
            return
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia):
            fraction, self._pending_seek = self._pending_seek, None
            self.player.setPosition(int(fraction * self.player.duration()))
            self.player.play()
        elif status == QMediaPlayer.InvalidMedia:
            self._pending_seek = None

    def _on_cover_loaded(self, path: str) -> None:
        row = self._current_row()
        if row and row["cover"] == path:
            self._update_detail()

    def _select_paths(self, paths: list[str], current: str | None) -> None:
        selection = QItemSelection()
        last = len(COLUMNS) - 1
        for path in paths:
            row = self.model.row_of(path)
            if row is not None:
                selection.select(self.model.index(row, 0), self.model.index(row, last))
        self.table.selectionModel().select(selection, QItemSelectionModel.ClearAndSelect)
        row = self.model.row_of(current) if current else None
        if row is not None:
            self.table.selectionModel().setCurrentIndex(self.model.index(row, 1),
                                                        QItemSelectionModel.NoUpdate)

    def _refresh_sidebar(self) -> None:
        # Biblioteca: toda la librería, historial y colecciones.
        selected_view = self.current_view()
        total, _pending = db.stats(self.conn)
        entries = [("Toda la librería", ("all", None), total),
                   ("Historial", ("history", None), db.history_count(self.conn)),
                   ("Duplicados", ("duplicates", None), db.duplicate_count(self.conn))]
        entries += [(f"▸ {c['name']}", ("collection", c["id"]), c["n"])
                    for c in db.list_collections(self.conn)]
        self.views.blockSignals(True)
        self.views.clear()
        for label, value, n in entries:
            item = QListWidgetItem(f"{label}  ({n})")
            item.setData(Qt.UserRole, value)
            self.views.addItem(item)
            if value == selected_view:
                self.views.setCurrentItem(item)
        if self.views.currentItem() is None:
            self.views.setCurrentRow(0)
        self.views.blockSignals(False)

        current = self.instruments.currentItem()
        selected = current.data(Qt.UserRole) if current else None
        counts = db.instrument_counts(self.conn)
        self.instruments.blockSignals(True)
        self.instruments.clear()
        entries = [("Todos", None, sum(counts.values()))]
        entries += sorted(
            ((INSTRUMENT_LABELS.get(k, k), k, n) for k, n in counts.items() if k),
            key=lambda e: e[0],
        )
        if counts.get(None):
            entries.append(("Sin clasificar", "__none__", counts[None]))
        for label, value, n in entries:
            item = QListWidgetItem(f"{label}  ({n})")
            item.setData(Qt.UserRole, value)
            self.instruments.addItem(item)
            if value == selected:
                self.instruments.setCurrentItem(item)
        if self.instruments.currentItem() is None:
            self.instruments.setCurrentRow(0)
        self.instruments.blockSignals(False)

        selected_tag = self.tag.currentData()
        self.tag.blockSignals(True)
        self.tag.clear()
        self.tag.addItem("Todos", None)
        for tag, n in db.all_tags(self.conn):
            self.tag.addItem(f"{tag}  ({n})", tag)
        self.tag.setCurrentIndex(max(0, self.tag.findData(selected_tag)))
        self.tag.blockSignals(False)

        self.roots.clear()
        self.roots.addItems(db.list_roots(self.conn))

    def _on_view_changed(self, *_args) -> None:
        # El historial va en orden de escucha y los duplicados agrupados: sin orden por columna.
        if self.current_view()[0] in ("history", "duplicates"):
            self.table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self._schedule_refresh()

    # --- Datos del usuario: favoritos, estrellas, colecciones, edición ---
    def selected_paths(self) -> list[str]:
        return [self.model.rows[i.row()]["path"]
                for i in self.table.selectionModel().selectedRows()]

    def _selected_rows(self) -> list[dict]:
        return [self.model.rows[i.row()] for i in self.table.selectionModel().selectedRows()]

    def _reload_rows(self, paths: list[str]) -> None:
        """Actualiza esas filas en la tabla sin recargar todo (no salta ni cambia el orden)."""
        self.model.update_rows(db.get_samples(self.conn, paths))
        self._update_detail()

    def toggle_favorite(self, paths: list[str] | None = None) -> None:
        """Marca como favoritos los elegidos; si ya lo eran todos, los desmarca."""
        rows = ([self.model.rows[self.model.row_of(p)] for p in paths] if paths
                else self._selected_rows())
        if not rows:
            return
        favorite = not all(r["favorite"] for r in rows)
        db.set_favorite(self.conn, [r["path"] for r in rows], favorite)
        self._reload_rows([r["path"] for r in rows])

    def set_rating(self, rating: int, paths: list[str] | None = None) -> None:
        paths = paths or self.selected_paths()
        if paths:
            db.set_rating(self.conn, paths, rating)
            self._reload_rows(paths)

    def _on_clicked(self, index: QModelIndex) -> None:
        """Clic en la estrella marca el favorito; clic en las estrellas pone esa cantidad
        (clic en la misma cantidad las borra)."""
        row = self.model.rows[index.row()]
        if index.column() == FAVORITE_COLUMN:
            self.toggle_favorite([row["path"]])
        elif index.column() == RATING_COLUMN:
            rect = self.table.visualRect(index)
            star = max(1, self.table.fontMetrics().horizontalAdvance("★"))
            x = self.table.viewport().mapFromGlobal(QCursor.pos()).x() - rect.left() - 3
            n = min(5, max(1, x // star + 1))
            self.set_rating(0 if n == row["rating"] else n, [row["path"]])

    def _on_double_clicked(self, index: QModelIndex) -> None:
        if index.column() not in (FAVORITE_COLUMN, RATING_COLUMN):
            self.play(index.row())

    def edit_selected(self) -> None:
        """Abre el diálogo de edición para las filas elegidas y guarda lo que cambió."""
        rows = self._selected_rows()
        if not rows:
            return
        dialog = EditDialog(self, rows, [t for t, _n in db.all_tags(self.conn)])
        if dialog.exec() != QDialog.Accepted:
            return
        fields, add, remove = dialog.changes()
        paths = [r["path"] for r in rows]
        for field, value in fields.items():
            db.set_user_field(self.conn, paths, field, value)
        if add:
            db.add_tags(self.conn, paths, add)
        if remove:
            db.remove_tags(self.conn, paths, remove)
        if fields or add or remove:
            self.refresh()

    def reset_selected(self) -> None:
        """Descarta las correcciones manuales: el próximo escaneo recalcula esos samples."""
        paths = self.selected_paths()
        if not paths:
            return
        db.clear_user_fields(self.conn, paths)
        if self.thread:
            self.statusBar().showMessage(
                "Se recalculan con el próximo Re-escanear (hay un análisis en curso).", 6000)
        else:
            self.start_scan()

    def new_collection(self, paths: list[str] | None = None) -> int | None:
        """Pide un nombre y crea la colección (con esos samples, si se pasan)."""
        name, ok = QInputDialog.getText(self, "Nueva colección", "Nombre:")
        if not ok or not name.strip():
            return None
        try:
            collection = db.create_collection(self.conn, name)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Nueva colección", f"Ya hay una colección «{name}».")
            return None
        if paths:
            db.add_to_collection(self.conn, collection, paths)
        self._refresh_sidebar()
        return collection

    def add_selected_to_collection(self, collection: int) -> None:
        db.add_to_collection(self.conn, collection, self.selected_paths())
        self._refresh_sidebar()

    def _on_dropped_to_collection(self, collection: int, paths: list[str]) -> None:
        db.add_to_collection(self.conn, collection, paths)
        self._refresh_sidebar()
        self.statusBar().showMessage(f"{len(paths)} sample(s) agregados a la colección.", 4000)

    def remove_selected_from_collection(self) -> None:
        view, collection = self.current_view()
        paths = self.selected_paths()
        if view == "collection" and paths:
            db.remove_from_collection(self.conn, collection, paths)
            self.refresh()

    def _views_menu(self, pos) -> None:
        item = self.views.itemAt(pos)
        menu = QMenu(self)
        menu.addAction("Nueva colección…", self.new_collection)
        view = item.data(Qt.UserRole) if item else None
        if view and view[0] == "collection":
            name = next(c["name"] for c in db.list_collections(self.conn) if c["id"] == view[1])
            menu.addAction("Renombrar…", lambda: self.rename_collection(view[1], name))
            menu.addAction("Borrar colección", lambda: self.delete_collection(view[1], name))
        elif view and view[0] == "history":
            menu.addAction("Vaciar historial", self.clear_history)
        menu.exec(self.views.viewport().mapToGlobal(pos))

    def rename_collection(self, collection: int, name: str) -> None:
        new, ok = QInputDialog.getText(self, "Renombrar colección", "Nombre:", text=name)
        if not ok or not new.strip() or new.strip() == name:
            return
        try:
            db.rename_collection(self.conn, collection, new)
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Renombrar colección", f"Ya hay una colección «{new}».")
            return
        self._refresh_sidebar()

    def delete_collection(self, collection: int, name: str) -> None:
        answer = QMessageBox.question(
            self, "Borrar colección",
            f"¿Borrar la colección «{name}»? Los samples siguen en la librería.")
        if answer == QMessageBox.Yes:
            db.delete_collection(self.conn, collection)
            self.refresh()

    def clear_history(self) -> None:
        db.clear_history(self.conn)
        self.refresh()

    # --- Carpetas y escaneo ---
    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Elegí una carpeta de samples")
        if folder:
            db.add_root(self.conn, folder.replace("/", "\\"))
            self.start_scan()

    def remove_folder(self) -> None:
        item = self.roots.currentItem()
        if item and not self.thread:
            db.remove_root(self.conn, item.text())
            self.refresh()

    def start_scan(self) -> None:
        """Indexa y analiza todas las carpetas en un LibraryWorker. No hace nada si ya hay uno."""
        if self.thread:
            return
        roots = db.list_roots(self.conn)
        if not roots:
            return
        self.thread = QThread(self)
        self.worker = LibraryWorker(roots)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.statusBar().showMessage)
        self.worker.indexed.connect(self.refresh)
        self.worker.finished.connect(self._scan_finished)
        self.thread.start()
        self.refresh()

    def _scan_finished(self) -> None:
        self.thread.quit()
        self.thread.wait()
        self.thread = self.worker = None
        self.statusBar().clearMessage()
        self.refresh()

    # --- Preescucha ---
    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        self._update_detail()
        if current.isValid() and self.autoplay.isChecked() and not self._restoring:
            self.play(current.row())

    def play(self, row: int, start: float | None = None) -> None:
        """Reproduce la fila (desde `start`, de 0 a 1, si se pasa) y la anota en el historial
        (la lista no se recarga, para no reordenar el historial mientras se lo recorre)."""
        path = self.model.rows[row]["path"]
        url = QUrl.fromLocalFile(path)
        self.player.stop()
        self._pending_seek = None
        if self.player.source() != url:
            self.player.setSource(url)
        if start is None:
            self.player.play()
        elif (self.player.duration() > 0 and self.player.mediaStatus() in (
                QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia, QMediaPlayer.EndOfMedia)):
            self.player.setPosition(int(start * self.player.duration()))
            self.player.play()
        else:  # todavía cargando: se salta al punto en _on_media_status
            self._pending_seek = start
        db.add_history(self.conn, path)

    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
        elif self.table.currentIndex().isValid():
            self.play(self.table.currentIndex().row())

    def _context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        path = self.model.rows[index.row()]["path"]
        rows = self._selected_rows()
        menu = QMenu(self)
        self.favorite_action.setText("Quitar de favoritos" if all(r["favorite"] for r in rows)
                                     else "Marcar como favorito")
        menu.addAction(self.favorite_action)
        rating_menu = menu.addMenu("Estrellas")
        rating_menu.addActions(self.rating_actions[1:] + self.rating_actions[:1])

        collections_menu = menu.addMenu("Agregar a colección")
        for c in db.list_collections(self.conn):
            collections_menu.addAction(
                c["name"], lambda c=c: self.add_selected_to_collection(c["id"]))
        if not collections_menu.isEmpty():
            collections_menu.addSeparator()
        collections_menu.addAction(
            "Nueva colección…", lambda: self.new_collection(self.selected_paths()))
        if self.current_view()[0] == "collection":
            menu.addAction(self.remove_from_collection_action)

        menu.addSeparator()
        menu.addAction(self.edit_action)
        if any(r[f"{f}_source"] == "user" for r in rows for f in db.EDITABLE_FIELDS):
            menu.addAction("Restablecer datos automáticos", self.reset_selected)
        copies = db.copies_of(self.conn, path) if self.model.rows[index.row()]["copies"] > 1 \
            else []
        if copies:
            copies_menu = menu.addMenu(f"Ir a otra copia ({len(copies)})")
            for copy in copies:
                copies_menu.addAction(copy, lambda copy=copy: self.go_to(copy))
        menu.addSeparator()
        menu.addAction("Mostrar en el Explorador",
                       lambda: subprocess.Popen(["explorer", "/select,", path]))
        menu.addAction("Copiar ruta", lambda: QGuiApplication.clipboard().setText(path))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # --- Actualización ---
    def _on_update_checked(self, info: dict) -> None:
        self.update_info = info
        if not info.get("available"):
            return
        text = f"<b>Hay una versión nueva: {info['latest']}</b> (tenés la {info['current']})."
        if info["reason"] == "git":
            text += " Estás usando el código del repositorio: actualizá con git pull."
        elif info["reason"] == "installer":
            text += " Esta versión se instala con el instalador completo."
        self.banner_text.setText(text)
        self.banner_update.setVisible(info["reason"] != "git")
        self.banner_update.setText("Descargar instalador" if info["reason"] == "installer"
                                   else "Actualizar")
        self.banner.show()

    def open_release_page(self) -> None:
        # Solo la página que devolvió la API de GitHub
        page = self.update_info.get("page", "")
        if page.startswith("https://"):
            QDesktopServices.openUrl(QUrl(page))

    def apply_update(self) -> None:
        """Botón del aviso: frena el análisis, aplica la actualización en otro hilo y reinicia."""
        if self.update_info.get("reason") == "installer":
            self.open_release_page()
            return
        if self.thread:  # que el análisis no escriba mientras se reemplazan los archivos
            self.worker.stop()
            self.statusBar().showMessage("Deteniendo el análisis…")
            self.thread.quit()
            self.thread.wait(10000)
        self.banner_update.setEnabled(False)
        self.run_task(updater.apply, self._on_update_applied, self._on_update_failed)

    def _on_update_applied(self, version: str) -> None:
        self.statusBar().showMessage(f"Sample Scout {version} instalado. Reiniciando…")
        updater.restart()
        QTimer.singleShot(800, self.close)

    def _on_update_failed(self, exc: Exception) -> None:
        self.banner_update.setEnabled(True)
        self.statusBar().clearMessage()
        if isinstance(exc, updater.NeedsInstaller):
            answer = QMessageBox.question(
                self, "Hace falta el instalador",
                "Esta versión cambia el Python que trae la app y se instala con el instalador "
                "completo. Instalalo encima: no se pierde nada (tu librería queda igual).\n\n"
                "¿Abrir la página de descarga?")
            if answer == QMessageBox.Yes:
                self.open_release_page()
            return
        QMessageBox.warning(self, "No se pudo actualizar", f"No se pudo actualizar: {exc}.")

    # --- Columnas: cuáles se ven, en qué orden y con qué ancho ---
    def _settings(self) -> QSettings:
        # Al lado de la base: con SAMPLE_SCOUT_DB las pruebas no tocan la configuración real.
        return QSettings(str(db.default_db_path().parent / "settings.ini"), QSettings.IniFormat)

    def _header_menu(self, pos) -> None:
        header = self.table.horizontalHeader()
        menu = QMenu(self)
        visible = [i for i in range(len(COLUMNS)) if not header.isSectionHidden(i)]
        for i in sorted(range(len(COLUMNS)), key=header.visualIndex):
            field, label = COLUMNS[i]
            action = menu.addAction(COLUMN_MENU_LABELS.get(field, label))
            action.setCheckable(True)
            action.setChecked(i in visible)
            action.setEnabled(visible != [i])  # al menos una columna a la vista
            action.toggled.connect(lambda on, i=i: self._set_column_visible(i, on))
        menu.addSeparator()
        menu.addAction("Restablecer columnas", self.reset_columns)
        menu.exec(header.viewport().mapToGlobal(pos))

    def _set_column_visible(self, column: int, visible: bool) -> None:
        header = self.table.horizontalHeader()
        header.setSectionHidden(column, not visible)
        if visible and header.sectionSize(column) < 20:
            header.resizeSection(column, COLUMN_WIDTHS[column])
        self._save_columns()

    def reset_columns(self) -> None:
        """Todas las columnas a la vista, en el orden y el ancho de fábrica."""
        header = self.table.horizontalHeader()
        for i in range(len(COLUMNS)):
            header.moveSection(header.visualIndex(i), i)
            header.setSectionHidden(i, COLUMNS[i][0] in DEFAULT_HIDDEN)
            header.resizeSection(i, COLUMN_WIDTHS[i])
        self._settings().remove("columns")

    def _save_columns(self) -> None:
        """Guarda por nombre de campo (no con header.saveState()): si una versión nueva suma
        columnas, el estado viejo sigue sirviendo y las nuevas aparecen a la vista (salvo las de
        DEFAULT_HIDDEN, que son opcionales)."""
        header = self.table.horizontalHeader()
        state = {field: {"pos": header.visualIndex(i), "hidden": header.isSectionHidden(i),
                         "width": header.sectionSize(i) or COLUMN_WIDTHS[i]}
                 for i, (field, _label) in enumerate(COLUMNS)}
        self._settings().setValue("columns", json.dumps(state))

    def _restore_columns(self) -> None:
        try:
            state = json.loads(self._settings().value("columns", "") or "{}")
        except (TypeError, ValueError):
            return
        if not isinstance(state, dict):
            return
        fields = [field for field, _label in COLUMNS]
        known = sorted((f for f in fields if f in state), key=lambda f: state[f].get("pos", 0))
        order = known[:]
        for i, field in enumerate(fields):  # las columnas nuevas, en su lugar de fábrica
            if field not in state:
                order.insert(min(i, len(order)), field)
        header = self.table.horizontalHeader()
        for pos, field in enumerate(order):
            i = fields.index(field)
            header.moveSection(header.visualIndex(i), pos)
            saved = state.get(field, {})
            header.setSectionHidden(i, bool(saved.get("hidden", field in DEFAULT_HIDDEN)))
            width = saved.get("width")
            if isinstance(width, int) and width >= 20:
                header.resizeSection(i, width)
        if all(header.isSectionHidden(i) for i in range(len(fields))):
            header.setSectionHidden(NAME_COLUMN, False)

    def closeEvent(self, event) -> None:
        self._save_columns()
        if self.worker:
            self.worker.stop()
            self.thread.quit()
            self.thread.wait(5000)
        super().closeEvent(event)


def _setup_logging() -> None:
    """Con pythonw no hay consola: los errores van a %APPDATA%\\SampleScout\\app.log."""
    if sys.stderr is not None:
        return
    log = open(db.default_db_path().parent / "app.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log

    def hook(exc_type, exc, tb):
        traceback.print_exception(exc_type, exc, tb, file=log)

    sys.excepthook = hook


def main() -> None:
    """Punto de entrada (`python -m sample_scout` y el script `sample-scout`)."""
    multiprocessing.freeze_support()
    _setup_logging()
    if os.name == "nt":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    app = QApplication(sys.argv)
    app.setApplicationName("Sample Scout")
    icon = APP_DIR / "icon.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
