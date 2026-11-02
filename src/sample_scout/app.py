"""Ventana principal: filtros, lista de samples, preescucha y arrastre al DAW."""

from __future__ import annotations

import multiprocessing
import os
import subprocess
import sys
import traceback

from PySide6.QtCore import (QAbstractTableModel, QMimeData, QModelIndex, QObject, Qt, QThread,
                            QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
                               QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QSpinBox, QSplitter, QTableView,
                               QToolBar, QVBoxLayout, QWidget)

from sample_scout import APP_DIR, __version__, db, scanner, updater
from sample_scout.analyzer import NOTES
from sample_scout.parser import INSTRUMENT_LABELS

# Igual que el AppUserModelID de los accesos directos del instalador: así la ventana y el
# acceso directo son la misma app en la barra de tareas
APP_USER_MODEL_ID = "LeandroDoliri.SampleScout"

COLUMNS = [
    ("name", "Nombre"), ("instrument", "Instrumento"), ("kind", "Tipo"), ("bpm", "BPM"),
    ("key", "Key"), ("duration", "Duración"), ("folder", "Carpeta"),
]
KIND_LABELS = {"loop": "Loop", "oneshot": "One-shot"}


class SampleModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

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
            if row["error"]:
                tip += f"\nError: {row['error']}"
            return tip
        if role == Qt.TextAlignmentRole and field in ("bpm", "duration"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def sort(self, column, order=Qt.AscendingOrder) -> None:
        field = COLUMNS[column][0]
        numeric = field in ("bpm", "duration")
        filled = [r for r in self.rows if r[field] is not None]
        empty = [r for r in self.rows if r[field] is None]  # siempre al final
        filled.sort(key=lambda r: r[field] if numeric else str(r[field]).lower(),
                    reverse=order == Qt.DescendingOrder)
        self.beginResetModel()
        self.rows = filled + empty
        self.endResetModel()

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
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Sample Scout {__version__}")
        self.resize(1300, 800)
        self.conn = db.connect()
        self.thread: QThread | None = None
        self.worker: LibraryWorker | None = None
        self.tasks: list[tuple[QThread, TaskWorker]] = []  # referencias vivas mientras corren
        self.update_info: dict = {}

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)

        self._build_ui()
        self.search_timer = QTimer(self, singleShot=True, interval=200)
        self.search_timer.timeout.connect(self.refresh)
        self.refresh()
        if db.list_roots(self.conn):
            self.start_scan()
        self.run_task(lambda _log: updater.check(), self._on_update_checked)

    def run_task(self, fn, on_done, on_failed=None) -> None:
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
        self.search = QLineEdit(placeholderText="Buscar (nombre, carpeta, pack…)", clearButtonEnabled=True)
        self.search.setMaximumWidth(420)
        self.search.textChanged.connect(self._schedule_refresh)
        toolbar.addWidget(self.search)

        # Panel izquierdo: categorías y filtros.
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
        self.key = QComboBox()
        self.key.addItem("Todas", None)
        for note in NOTES:
            self.key.addItem(note, note)
            self.key.addItem(note + "m", note + "m")
        self.key.currentIndexChanged.connect(self._schedule_refresh)
        self.autoplay = QCheckBox("Escuchar al seleccionar", checked=True)

        filters = QFormLayout()
        filters.addRow("Tipo", self.kind)
        bpm_row = QHBoxLayout()
        bpm_row.addWidget(self.bpm_min)
        bpm_row.addWidget(QLabel("a"))
        bpm_row.addWidget(self.bpm_max)
        filters.addRow("BPM", bpm_row)
        filters.addRow("Key", self.key)

        self.roots = QListWidget()
        self.roots.setMaximumHeight(120)
        remove_root = QPushButton("Quitar carpeta")
        remove_root.clicked.connect(self.remove_folder)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("<b>Instrumento</b>"))
        left_layout.addWidget(self.instruments, 1)
        left_layout.addLayout(filters)
        left_layout.addWidget(self.autoplay)
        left_layout.addWidget(QLabel("<b>Carpetas</b>"))
        left_layout.addWidget(self.roots)
        left_layout.addWidget(remove_root)

        # Tabla central.
        self.model = SampleModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setDragEnabled(True)
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        self.table.setDefaultDropAction(Qt.CopyAction)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(22)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        for col, width in enumerate((340, 100, 80, 60, 60, 80)):
            self.table.setColumnWidth(col, width)
        self.table.selectionModel().currentRowChanged.connect(self._on_current_changed)
        self.table.doubleClicked.connect(lambda index: self.play(index.row()))
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        play_action = QAction("Reproducir / detener", self, shortcut=QKeySequence(Qt.Key_Space))
        play_action.triggered.connect(self.toggle_play)
        self.table.addAction(play_action)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.table)
        splitter.setSizes([260, 1040])

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
    def refresh(self) -> None:
        self._refresh_sidebar()
        item = self.instruments.currentItem()
        rows = db.search(
            self.conn,
            text=self.search.text(),
            instrument=item.data(Qt.UserRole) if item else None,
            kind=self.kind.currentData(),
            bpm_min=self.bpm_min.value() or None,
            bpm_max=self.bpm_max.value() or None,
            key=self.key.currentData(),
        )
        self.model.set_rows(rows)
        total, pending = db.stats(self.conn)
        busy = " — trabajando…" if self.thread else ""
        self.status.setText(f"{len(rows)} de {total} samples · {pending} sin analizar{busy}")

    def _refresh_sidebar(self) -> None:
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

        self.roots.clear()
        self.roots.addItems(db.list_roots(self.conn))

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
        if current.isValid() and self.autoplay.isChecked():
            self.play(current.row())

    def play(self, row: int) -> None:
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(self.model.rows[row]["path"]))
        self.player.play()

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
        menu = QMenu(self)
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

    def closeEvent(self, event) -> None:
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
