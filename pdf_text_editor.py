"""
PDF Text Editor v2 - editor local para añadir, borrar y sustituir texto en PDF.

Funcionalidades principales:
- Abrir un fichero PDF.
- Navegar entre páginas.
- Añadir texto en cualquier página.
- Seleccionar texto existente mediante arrastre rectangular.
- Borrar texto existente mediante redacción PDF.
- Sustituir texto existente por otro texto.
- Cambiar características visuales del texto sustituido: tamaño, color y fuente.
- Guardar una copia del PDF modificado.

Dependencias:
    pip install PyMuPDF Pillow

Ejecución:
    python pdf_text_editor.py

Nota técnica importante:
Un PDF no es un documento editable como un DOCX. Normalmente contiene instrucciones
gráficas, texto posicionado y recursos tipográficos. Por ello, la edición robusta
del texto existente se implementa mediante:
    1) localización de palabras/bloques de texto;
    2) redacción del área seleccionada;
    3) inserción opcional de nuevo texto sobre el área redactada.

Este enfoque permite borrar o sustituir contenido de forma fiable, sin depender de
la estructura interna original del PDF.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image, ImageTk


ColorRGB = Tuple[float, float, float]


@dataclass
class TextStamp:
    """Representa una inserción de texto nuevo sobre una página PDF."""
    page_index: int
    x_pdf: float
    y_pdf: float
    text: str
    font_size: float = 12.0
    color_rgb: ColorRGB = (0.0, 0.0, 0.0)
    font_name: str = "helv"


@dataclass
class ExistingWord:
    """Representa una palabra detectada en el PDF."""
    page_index: int
    rect: fitz.Rect
    text: str
    block_no: int
    line_no: int
    word_no: int


@dataclass
class TextEdit:
    """
    Representa una operación sobre texto existente.

    Si replacement_text está vacío, la operación equivale a borrado.
    Si replacement_text contiene texto, la operación equivale a sustitución.
    """
    page_index: int
    rect: fitz.Rect
    original_text: str
    replacement_text: str = ""
    font_size: float = 12.0
    color_rgb: ColorRGB = (0.0, 0.0, 0.0)
    font_name: str = "helv"


class PDFTextEditor(tk.Tk):
    """Aplicación de escritorio para añadir, borrar y sustituir texto en PDF."""

    def __init__(self) -> None:
        super().__init__()

        self.title("Editor de texto para PDF - Python")
        self.geometry("1280x880")
        self.minsize(1100, 740)

        self.pdf_path: Optional[Path] = None
        self.doc: Optional[fitz.Document] = None
        self.current_page_index: int = 0

        # Factor de renderizado. 1 punto PDF equivale a zoom píxeles en pantalla.
        self.zoom: float = 1.5

        self.page_image_tk: Optional[ImageTk.PhotoImage] = None
        self.page_image_id: Optional[int] = None

        self.stamps_by_page: Dict[int, List[TextStamp]] = {}
        self.edits_by_page: Dict[int, List[TextEdit]] = {}
        self.words_by_page: Dict[int, List[ExistingWord]] = {}

        self.selected_stamp_index: Optional[int] = None
        self.selected_edit_index: Optional[int] = None
        self.selected_words: List[ExistingWord] = []

        self.current_color_rgb: ColorRGB = (0.0, 0.0, 0.0)
        self.current_color_hex: str = "#000000"

        self.mode_var = tk.StringVar(value="insert")

        # Estado de selección por arrastre.
        self.drag_start_canvas: Optional[Tuple[float, float]] = None
        self.drag_rect_canvas_id: Optional[int] = None

        self._build_ui()
        self._set_state_without_pdf()

    # ------------------------------------------------------------------
    # Interfaz
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=6)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(20, weight=1)

        ttk.Button(toolbar, text="Abrir PDF", command=self.open_pdf).grid(row=0, column=0, padx=2)
        ttk.Button(toolbar, text="Guardar como...", command=self.save_pdf_as).grid(row=0, column=1, padx=2)

        ttk.Separator(toolbar, orient="vertical").grid(row=0, column=2, sticky="ns", padx=8)

        ttk.Button(toolbar, text="◀ Página", command=self.prev_page).grid(row=0, column=3, padx=2)
        ttk.Button(toolbar, text="Página ▶", command=self.next_page).grid(row=0, column=4, padx=2)

        self.page_label = ttk.Label(toolbar, text="Página -/-")
        self.page_label.grid(row=0, column=5, padx=10)

        ttk.Label(toolbar, text="Zoom").grid(row=0, column=6, padx=(12, 2))
        self.zoom_var = tk.DoubleVar(value=self.zoom)
        self.zoom_combo = ttk.Combobox(
            toolbar,
            textvariable=self.zoom_var,
            values=[0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0],
            width=6,
            state="readonly",
        )
        self.zoom_combo.grid(row=0, column=7, padx=2)
        self.zoom_combo.bind("<<ComboboxSelected>>", lambda _: self.change_zoom())

        main = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        main.grid(row=1, column=0, sticky="nsew")

        canvas_frame = ttk.Frame(main)
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(canvas_frame, background="#777777", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")

        x_scroll = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")

        self.canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)

        side = ttk.Frame(main, padding=10)
        side.columnconfigure(0, weight=1)

        main.add(canvas_frame, weight=4)
        main.add(side, weight=1)

        mode_frame = ttk.LabelFrame(side, text="Modo de trabajo", padding=8)
        mode_frame.grid(row=0, column=0, sticky="ew")
        mode_frame.columnconfigure(0, weight=1)

        ttk.Radiobutton(
            mode_frame,
            text="Añadir texto nuevo",
            variable=self.mode_var,
            value="insert",
            command=self.on_mode_changed,
        ).grid(row=0, column=0, sticky="w")

        ttk.Radiobutton(
            mode_frame,
            text="Seleccionar texto existente",
            variable=self.mode_var,
            value="select",
            command=self.on_mode_changed,
        ).grid(row=1, column=0, sticky="w")

        ttk.Label(side, text="Texto", font=("Segoe UI", 11, "bold")).grid(row=1, column=0, sticky="w", pady=(10, 0))

        self.text_box = tk.Text(side, height=6, wrap="word")
        self.text_box.grid(row=2, column=0, sticky="ew", pady=(4, 12))
        self.text_box.insert("1.0", "Texto de ejemplo")

        props = ttk.LabelFrame(side, text="Propiedades del texto nuevo/sustituido", padding=8)
        props.grid(row=3, column=0, sticky="ew", pady=6)
        props.columnconfigure(1, weight=1)

        ttk.Label(props, text="Tamaño").grid(row=0, column=0, sticky="w")
        self.font_size_var = tk.DoubleVar(value=12.0)
        ttk.Spinbox(props, textvariable=self.font_size_var, from_=4, to=96, increment=1, width=8).grid(
            row=0, column=1, sticky="ew", padx=4
        )

        ttk.Label(props, text="Fuente").grid(row=1, column=0, sticky="w", pady=4)
        self.font_name_var = tk.StringVar(value="helv")
        font_combo = ttk.Combobox(
            props,
            textvariable=self.font_name_var,
            values=["helv", "tiro", "cour", "times", "symbol"],
            state="readonly",
            width=10,
        )
        font_combo.grid(row=1, column=1, sticky="ew", padx=4, pady=4)

        ttk.Button(props, text="Elegir color", command=self.choose_color).grid(row=2, column=0, sticky="ew", pady=4)
        self.color_preview = tk.Label(
            props,
            text=self.current_color_hex,
            background=self.current_color_hex,
            foreground="white",
        )
        self.color_preview.grid(row=2, column=1, sticky="ew", padx=4, pady=4)

        actions = ttk.LabelFrame(side, text="Acciones sobre texto existente", padding=8)
        actions.grid(row=4, column=0, sticky="ew", pady=8)
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        ttk.Button(actions, text="Borrar seleccionado", command=self.delete_selected_existing_text).grid(
            row=0, column=0, sticky="ew", padx=2, pady=2
        )
        ttk.Button(actions, text="Sustituir seleccionado", command=self.replace_selected_existing_text).grid(
            row=0, column=1, sticky="ew", padx=2, pady=2
        )

        ttk.Button(actions, text="Cambiar estilo manteniendo texto", command=self.restyle_selected_existing_text).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=2, pady=2
        )
        ttk.Button(actions, text="Limpiar selección", command=self.clear_existing_selection).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=2, pady=2
        )

        help_text = (
            "Uso recomendado:\n"
            "• Para añadir: modo «Añadir texto nuevo» y clic en la página.\n"
            "• Para borrar/sustituir: modo «Seleccionar texto existente», "
            "arrastre un rectángulo sobre el texto y aplique la acción.\n\n"
            "Advertencia: la sustitución se realiza redactando el texto "
            "seleccionado y escribiendo texto nuevo encima."
        )
        ttk.Label(side, text=help_text, justify="left", wraplength=330).grid(
            row=5, column=0, sticky="ew", pady=(4, 10)
        )

        ttk.Label(side, text="Operaciones de la página", font=("Segoe UI", 11, "bold")).grid(
            row=6, column=0, sticky="w"
        )

        self.operation_list = tk.Listbox(side, height=12)
        self.operation_list.grid(row=7, column=0, sticky="nsew", pady=4)
        self.operation_list.bind("<<ListboxSelect>>", self.on_operation_selected)

        side.rowconfigure(7, weight=1)

        buttons = ttk.Frame(side)
        buttons.grid(row=8, column=0, sticky="ew", pady=6)
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)

        ttk.Button(buttons, text="Eliminar operación", command=self.delete_selected_operation).grid(
            row=0, column=0, sticky="ew", padx=2
        )
        ttk.Button(buttons, text="Limpiar página", command=self.clear_current_page_operations).grid(
            row=0, column=1, sticky="ew", padx=2
        )

        self.status_var = tk.StringVar(value="Abra un PDF para comenzar.")
        status = ttk.Label(self, textvariable=self.status_var, anchor="w", padding=6)
        status.grid(row=2, column=0, sticky="ew")

    def _set_state_without_pdf(self) -> None:
        self.page_label.configure(text="Página -/-")
        self.status_var.set("Abra un PDF para comenzar.")

    # ------------------------------------------------------------------
    # Operaciones sobre PDF
    # ------------------------------------------------------------------

    def open_pdf(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar PDF",
            filetypes=[("PDF", "*.pdf"), ("Todos los ficheros", "*.*")]
        )
        if not path:
            return

        try:
            doc = fitz.open(path)
            if doc.page_count == 0:
                raise ValueError("El PDF no contiene páginas.")
        except Exception as exc:
            messagebox.showerror("Error al abrir PDF", f"No se pudo abrir el PDF:\n{exc}")
            return

        self.pdf_path = Path(path)
        self.doc = doc
        self.current_page_index = 0

        self.stamps_by_page.clear()
        self.edits_by_page.clear()
        self.words_by_page.clear()
        self.selected_words.clear()
        self.selected_stamp_index = None
        self.selected_edit_index = None

        self.render_current_page()
        self.status_var.set(f"PDF abierto: {self.pdf_path.name}")

    def save_pdf_as(self) -> None:
        if self.doc is None or self.pdf_path is None:
            messagebox.showwarning("Sin PDF", "Primero debe abrir un fichero PDF.")
            return

        output = filedialog.asksaveasfilename(
            title="Guardar PDF como",
            defaultextension=".pdf",
            initialfile=f"{self.pdf_path.stem}_editado.pdf",
            filetypes=[("PDF", "*.pdf")]
        )
        if not output:
            return

        try:
            out_doc = fitz.open(str(self.pdf_path))

            # 1) Aplicar redacciones de texto existente.
            for page_index, edits in self.edits_by_page.items():
                page = out_doc[page_index]
                for edit in edits:
                    page.add_redact_annot(edit.rect, fill=(1, 1, 1))

                if edits:
                    # graphics=0 evita eliminar líneas o imágenes cercanas salvo que queden afectadas
                    # directamente por la redacción. En versiones antiguas de PyMuPDF puede ignorarse.
                    try:
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=0)
                    except TypeError:
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

            # 2) Insertar sustituciones de texto existente.
            for page_index, edits in self.edits_by_page.items():
                page = out_doc[page_index]
                for edit in edits:
                    if edit.replacement_text.strip():
                        self._insert_text_in_rect(
                            page=page,
                            rect=edit.rect,
                            text=edit.replacement_text,
                            font_size=edit.font_size,
                            font_name=edit.font_name,
                            color_rgb=edit.color_rgb,
                        )

            # 3) Insertar textos añadidos libremente.
            for page_index, stamps in self.stamps_by_page.items():
                page = out_doc[page_index]
                for stamp in stamps:
                    page.insert_text(
                        point=fitz.Point(stamp.x_pdf, stamp.y_pdf),
                        text=stamp.text,
                        fontsize=stamp.font_size,
                        fontname=stamp.font_name,
                        color=stamp.color_rgb,
                        overlay=True,
                    )

            out_doc.save(output, garbage=4, deflate=True)
            out_doc.close()

        except Exception as exc:
            messagebox.showerror("Error al guardar", f"No se pudo guardar el PDF:\n{exc}")
            return

        self.status_var.set(f"PDF guardado: {Path(output).name}")
        messagebox.showinfo("PDF guardado", f"El PDF se ha guardado correctamente:\n{output}")

    def _insert_text_in_rect(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        text: str,
        font_size: float,
        font_name: str,
        color_rgb: ColorRGB,
    ) -> None:
        """
        Inserta texto dentro del rectángulo del texto redactado.

        Si el texto no cabe, se reduce gradualmente el tamaño de fuente.
        """
        if not text.strip():
            return

        # Añadimos un pequeño margen interior.
        target = fitz.Rect(rect.x0, rect.y0, rect.x1 + 2, rect.y1 + max(2, font_size * 0.4))

        size = float(font_size)
        while size >= 4:
            rc = page.insert_textbox(
                rect=target,
                buffer=text,
                fontsize=size,
                fontname=font_name,
                color=color_rgb,
                align=fitz.TEXT_ALIGN_LEFT,
                overlay=True,
            )
            # En PyMuPDF, rc >= 0 suele indicar espacio restante; rc < 0 indica que no cabe.
            if rc >= 0:
                return
            size -= 0.5

        # Último recurso: insertar en la esquina superior izquierda.
        page.insert_text(
            point=fitz.Point(target.x0, target.y0 + max(4, font_size)),
            text=text,
            fontsize=max(4, size),
            fontname=font_name,
            color=color_rgb,
            overlay=True,
        )

    # ------------------------------------------------------------------
    # Extracción y renderizado
    # ------------------------------------------------------------------

    def get_words_for_page(self, page_index: int) -> List[ExistingWord]:
        if self.doc is None:
            return []

        if page_index in self.words_by_page:
            return self.words_by_page[page_index]

        page = self.doc[page_index]
        raw_words = page.get_text("words")
        words: List[ExistingWord] = []

        for item in raw_words:
            # Formato habitual:
            # x0, y0, x1, y1, word, block_no, line_no, word_no
            x0, y0, x1, y1, text, block_no, line_no, word_no = item[:8]
            words.append(
                ExistingWord(
                    page_index=page_index,
                    rect=fitz.Rect(x0, y0, x1, y1),
                    text=str(text),
                    block_no=int(block_no),
                    line_no=int(line_no),
                    word_no=int(word_no),
                )
            )

        self.words_by_page[page_index] = words
        return words

    def render_current_page(self) -> None:
        if self.doc is None:
            return

        page = self.doc[self.current_page_index]
        matrix = fitz.Matrix(self.zoom, self.zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)

        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.page_image_tk = ImageTk.PhotoImage(image)

        self.canvas.delete("all")
        self.page_image_id = self.canvas.create_image(0, 0, image=self.page_image_tk, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, pix.width, pix.height))

        self.page_label.configure(text=f"Página {self.current_page_index + 1}/{self.doc.page_count}")

        self.selected_stamp_index = None
        self.selected_edit_index = None
        self.selected_words.clear()

        self.draw_all_overlays()
        self.refresh_operation_list()

    def draw_all_overlays(self) -> None:
        self.canvas.delete("overlay")
        self.draw_existing_selection()
        self.draw_pending_edits()
        self.draw_stamps()

    def draw_existing_selection(self) -> None:
        for word in self.selected_words:
            x0, y0, x1, y1 = self.pdf_rect_to_canvas_tuple(word.rect)
            self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline="#0078D7",
                width=2,
                tags=("overlay", "selection"),
            )

    def draw_pending_edits(self) -> None:
        edits = self.edits_by_page.get(self.current_page_index, [])
        for idx, edit in enumerate(edits):
            x0, y0, x1, y1 = self.pdf_rect_to_canvas_tuple(edit.rect)
            outline = "#D83B01" if idx != self.selected_edit_index else "#B4009E"
            self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline=outline,
                width=2,
                dash=(4, 2),
                tags=("overlay", "edit"),
            )
            label = "BORRAR" if not edit.replacement_text.strip() else "SUSTITUIR"
            self.canvas.create_text(
                x0 + 3,
                max(0, y0 - 12),
                text=label,
                anchor="nw",
                fill=outline,
                font=("Arial", 8, "bold"),
                tags=("overlay", "edit"),
            )

    def draw_stamps(self) -> None:
        stamps = self.stamps_by_page.get(self.current_page_index, [])
        for idx, stamp in enumerate(stamps):
            x_canvas = stamp.x_pdf * self.zoom
            y_canvas = stamp.y_pdf * self.zoom
            color_hex = self.rgb_tuple_to_hex(stamp.color_rgb)
            tag = f"stamp_{idx}"

            self.canvas.create_text(
                x_canvas,
                y_canvas,
                text=stamp.text,
                anchor="nw",
                fill=color_hex,
                font=("Arial", max(1, int(stamp.font_size * self.zoom))),
                tags=("overlay", "stamp", tag),
            )

            if idx == self.selected_stamp_index:
                bbox = self.canvas.bbox(tag)
                if bbox:
                    x1, y1, x2, y2 = bbox
                    self.canvas.create_rectangle(
                        x1 - 3, y1 - 3, x2 + 3, y2 + 3,
                        outline="#107C10",
                        width=2,
                        tags=("overlay",)
                    )

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------

    def prev_page(self) -> None:
        if self.doc is None:
            return
        if self.current_page_index > 0:
            self.current_page_index -= 1
            self.render_current_page()

    def next_page(self) -> None:
        if self.doc is None:
            return
        if self.current_page_index < self.doc.page_count - 1:
            self.current_page_index += 1
            self.render_current_page()

    def change_zoom(self) -> None:
        try:
            self.zoom = float(self.zoom_var.get())
        except ValueError:
            self.zoom = 1.5
        self.render_current_page()

    # ------------------------------------------------------------------
    # Eventos de ratón
    # ------------------------------------------------------------------

    def on_canvas_press(self, event: tk.Event) -> None:
        if self.doc is None:
            return

        if self.mode_var.get() == "select":
            x = self.canvas.canvasx(event.x)
            y = self.canvas.canvasy(event.y)
            self.drag_start_canvas = (x, y)
            if self.drag_rect_canvas_id is not None:
                self.canvas.delete(self.drag_rect_canvas_id)
            self.drag_rect_canvas_id = self.canvas.create_rectangle(
                x, y, x, y,
                outline="#0078D7",
                width=2,
                dash=(3, 2),
                tags=("drag_selection",)
            )

    def on_canvas_drag(self, event: tk.Event) -> None:
        if self.doc is None or self.mode_var.get() != "select":
            return
        if self.drag_start_canvas is None or self.drag_rect_canvas_id is None:
            return

        x0, y0 = self.drag_start_canvas
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)
        self.canvas.coords(self.drag_rect_canvas_id, x0, y0, x1, y1)

    def on_canvas_release(self, event: tk.Event) -> None:
        if self.doc is None or self.mode_var.get() != "select":
            return
        if self.drag_start_canvas is None:
            return

        x0, y0 = self.drag_start_canvas
        x1 = self.canvas.canvasx(event.x)
        y1 = self.canvas.canvasy(event.y)
        self.drag_start_canvas = None

        if self.drag_rect_canvas_id is not None:
            self.canvas.delete(self.drag_rect_canvas_id)
            self.drag_rect_canvas_id = None

        # Ignorar microarrastres. El clic simple queda gestionado por on_canvas_click.
        if abs(x1 - x0) < 4 and abs(y1 - y0) < 4:
            return

        rect_canvas = self.normalized_canvas_rect(x0, y0, x1, y1)
        rect_pdf = self.canvas_rect_to_pdf_rect(rect_canvas)

        self.select_existing_words_in_rect(rect_pdf)

    def on_canvas_click(self, event: tk.Event) -> None:
        if self.doc is None:
            return

        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)

        if self.mode_var.get() == "select":
            # Selección de palabra individual mediante clic.
            word = self.find_word_at_canvas_position(canvas_x, canvas_y)
            if word is not None:
                self.selected_words = [word]
                self.text_box.delete("1.0", "end")
                self.text_box.insert("1.0", word.text)
                self.selected_edit_index = None
                self.selected_stamp_index = None
                self.draw_all_overlays()
                self.status_var.set(f"Palabra seleccionada: {word.text}")
            return

        # Modo inserción.
        clicked_index = self.find_stamp_at_canvas_position(canvas_x, canvas_y)
        if clicked_index is not None:
            self.selected_stamp_index = clicked_index
            self.selected_edit_index = None
            self.refresh_operation_list()
            self.draw_all_overlays()
            return

        text = self.text_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Texto vacío", "Escriba el texto que desea insertar.")
            return

        page = self.doc[self.current_page_index]
        page_rect = page.rect

        x_pdf = canvas_x / self.zoom
        y_pdf = canvas_y / self.zoom

        if not (0 <= x_pdf <= page_rect.width and 0 <= y_pdf <= page_rect.height):
            return

        stamp = TextStamp(
            page_index=self.current_page_index,
            x_pdf=x_pdf,
            y_pdf=y_pdf,
            text=text,
            font_size=float(self.font_size_var.get()),
            color_rgb=self.current_color_rgb,
            font_name=self.font_name_var.get(),
        )

        self.stamps_by_page.setdefault(self.current_page_index, []).append(stamp)
        self.selected_stamp_index = len(self.stamps_by_page[self.current_page_index]) - 1
        self.selected_edit_index = None

        self.draw_all_overlays()
        self.refresh_operation_list()
        self.status_var.set(
            f"Texto añadido en página {self.current_page_index + 1}, "
            f"x={x_pdf:.1f}, y={y_pdf:.1f} puntos PDF."
        )

    # ------------------------------------------------------------------
    # Selección y edición de texto existente
    # ------------------------------------------------------------------

    def select_existing_words_in_rect(self, rect_pdf: fitz.Rect) -> None:
        words = self.get_words_for_page(self.current_page_index)
        selected = [word for word in words if word.rect.intersects(rect_pdf)]

        # Orden natural de lectura aproximado.
        selected.sort(key=lambda w: (w.block_no, w.line_no, w.word_no))

        self.selected_words = selected
        self.selected_stamp_index = None
        self.selected_edit_index = None

        selected_text = self.reconstruct_selected_text(selected)
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", selected_text)

        self.draw_all_overlays()

        if selected:
            self.status_var.set(f"{len(selected)} palabra(s) seleccionada(s).")
        else:
            self.status_var.set("No se detectó texto en el área seleccionada.")

    def reconstruct_selected_text(self, words: List[ExistingWord]) -> str:
        if not words:
            return ""

        lines: Dict[Tuple[int, int], List[ExistingWord]] = {}
        for word in words:
            lines.setdefault((word.block_no, word.line_no), []).append(word)

        text_lines = []
        for key in sorted(lines.keys()):
            line_words = sorted(lines[key], key=lambda w: w.word_no)
            text_lines.append(" ".join(w.text for w in line_words))

        return "\n".join(text_lines)

    def get_selected_words_union_rect(self) -> Optional[fitz.Rect]:
        if not self.selected_words:
            return None

        rect = fitz.Rect(self.selected_words[0].rect)
        for word in self.selected_words[1:]:
            rect |= word.rect

        # Pequeña expansión para cubrir ascendentes, descendentes y pequeñas diferencias de renderizado.
        rect.x0 -= 1.5
        rect.y0 -= 1.5
        rect.x1 += 1.5
        rect.y1 += 2.0
        return rect

    def delete_selected_existing_text(self) -> None:
        rect = self.get_selected_words_union_rect()
        if rect is None:
            messagebox.showwarning("Sin selección", "Seleccione primero texto existente en el PDF.")
            return

        original = self.reconstruct_selected_text(self.selected_words)

        edit = TextEdit(
            page_index=self.current_page_index,
            rect=rect,
            original_text=original,
            replacement_text="",
            font_size=float(self.font_size_var.get()),
            color_rgb=self.current_color_rgb,
            font_name=self.font_name_var.get(),
        )

        self.edits_by_page.setdefault(self.current_page_index, []).append(edit)
        self.clear_existing_selection(redraw=False)
        self.selected_edit_index = len(self.edits_by_page[self.current_page_index]) - 1
        self.draw_all_overlays()
        self.refresh_operation_list()
        self.status_var.set("Operación de borrado añadida. Se aplicará al guardar.")

    def replace_selected_existing_text(self) -> None:
        rect = self.get_selected_words_union_rect()
        if rect is None:
            messagebox.showwarning("Sin selección", "Seleccione primero texto existente en el PDF.")
            return

        replacement = self.text_box.get("1.0", "end").strip()
        if not replacement:
            messagebox.showwarning("Texto vacío", "Escriba el texto de sustitución.")
            return

        original = self.reconstruct_selected_text(self.selected_words)

        edit = TextEdit(
            page_index=self.current_page_index,
            rect=rect,
            original_text=original,
            replacement_text=replacement,
            font_size=float(self.font_size_var.get()),
            color_rgb=self.current_color_rgb,
            font_name=self.font_name_var.get(),
        )

        self.edits_by_page.setdefault(self.current_page_index, []).append(edit)
        self.clear_existing_selection(redraw=False)
        self.selected_edit_index = len(self.edits_by_page[self.current_page_index]) - 1
        self.draw_all_overlays()
        self.refresh_operation_list()
        self.status_var.set("Operación de sustitución añadida. Se aplicará al guardar.")

    def restyle_selected_existing_text(self) -> None:
        """
        Cambia el estilo visual manteniendo el mismo contenido textual.

        Internamente equivale a redactar el texto seleccionado y reinsertar el mismo
        texto con las propiedades elegidas.
        """
        if not self.selected_words:
            messagebox.showwarning("Sin selección", "Seleccione primero texto existente en el PDF.")
            return

        original = self.reconstruct_selected_text(self.selected_words)
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", original)
        self.replace_selected_existing_text()

    def clear_existing_selection(self, redraw: bool = True) -> None:
        self.selected_words.clear()
        if redraw:
            self.draw_all_overlays()
        self.status_var.set("Selección limpiada.")

    # ------------------------------------------------------------------
    # Listado de operaciones
    # ------------------------------------------------------------------

    def refresh_operation_list(self) -> None:
        self.operation_list.delete(0, tk.END)

        edits = self.edits_by_page.get(self.current_page_index, [])
        for idx, edit in enumerate(edits):
            kind = "Borrar" if not edit.replacement_text.strip() else "Sustituir"
            original = edit.original_text.replace("\n", " ")
            if len(original) > 35:
                original = original[:32] + "..."
            self.operation_list.insert(tk.END, f"E{idx + 1}. {kind}: {original}")

        stamps = self.stamps_by_page.get(self.current_page_index, [])
        for idx, stamp in enumerate(stamps):
            preview = stamp.text.replace("\n", " ")
            if len(preview) > 35:
                preview = preview[:32] + "..."
            self.operation_list.insert(tk.END, f"T{idx + 1}. Añadir: {preview}")

        total_edits = len(edits)
        if self.selected_edit_index is not None and self.selected_edit_index < total_edits:
            self.operation_list.selection_set(self.selected_edit_index)
            self.operation_list.activate(self.selected_edit_index)
        elif self.selected_stamp_index is not None:
            row = total_edits + self.selected_stamp_index
            if row < self.operation_list.size():
                self.operation_list.selection_set(row)
                self.operation_list.activate(row)

    def on_operation_selected(self, _: tk.Event) -> None:
        selection = self.operation_list.curselection()
        if not selection:
            self.selected_edit_index = None
            self.selected_stamp_index = None
            self.draw_all_overlays()
            return

        row = int(selection[0])
        edits_count = len(self.edits_by_page.get(self.current_page_index, []))

        if row < edits_count:
            self.selected_edit_index = row
            self.selected_stamp_index = None
        else:
            self.selected_edit_index = None
            self.selected_stamp_index = row - edits_count

        self.draw_all_overlays()

    def delete_selected_operation(self) -> None:
        if self.selected_edit_index is not None:
            edits = self.edits_by_page.get(self.current_page_index, [])
            if 0 <= self.selected_edit_index < len(edits):
                del edits[self.selected_edit_index]
                self.selected_edit_index = None
                self.refresh_operation_list()
                self.draw_all_overlays()
                self.status_var.set("Operación sobre texto existente eliminada.")
                return

        if self.selected_stamp_index is not None:
            stamps = self.stamps_by_page.get(self.current_page_index, [])
            if 0 <= self.selected_stamp_index < len(stamps):
                del stamps[self.selected_stamp_index]
                self.selected_stamp_index = None
                self.refresh_operation_list()
                self.draw_all_overlays()
                self.status_var.set("Inserción de texto eliminada.")
                return

    def clear_current_page_operations(self) -> None:
        self.edits_by_page[self.current_page_index] = []
        self.stamps_by_page[self.current_page_index] = []
        self.selected_edit_index = None
        self.selected_stamp_index = None
        self.selected_words.clear()
        self.refresh_operation_list()
        self.draw_all_overlays()
        self.status_var.set("Operaciones de la página eliminadas.")

    # ------------------------------------------------------------------
    # Utilidades de detección
    # ------------------------------------------------------------------

    def find_word_at_canvas_position(self, x_canvas: float, y_canvas: float) -> Optional[ExistingWord]:
        x_pdf = x_canvas / self.zoom
        y_pdf = y_canvas / self.zoom

        for word in self.get_words_for_page(self.current_page_index):
            if word.rect.contains(fitz.Point(x_pdf, y_pdf)):
                return word

        return None

    def find_stamp_at_canvas_position(self, x: float, y: float) -> Optional[int]:
        stamps = self.stamps_by_page.get(self.current_page_index, [])
        for idx in reversed(range(len(stamps))):
            tag = f"stamp_{idx}"
            bbox = self.canvas.bbox(tag)
            if bbox:
                x1, y1, x2, y2 = bbox
                if x1 - 5 <= x <= x2 + 5 and y1 - 5 <= y <= y2 + 5:
                    return idx
        return None

    # ------------------------------------------------------------------
    # Utilidades geométricas y visuales
    # ------------------------------------------------------------------

    def normalized_canvas_rect(self, x0: float, y0: float, x1: float, y1: float) -> Tuple[float, float, float, float]:
        return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)

    def canvas_rect_to_pdf_rect(self, rect_canvas: Tuple[float, float, float, float]) -> fitz.Rect:
        x0, y0, x1, y1 = rect_canvas
        return fitz.Rect(x0 / self.zoom, y0 / self.zoom, x1 / self.zoom, y1 / self.zoom)

    def pdf_rect_to_canvas_tuple(self, rect_pdf: fitz.Rect) -> Tuple[float, float, float, float]:
        return (
            rect_pdf.x0 * self.zoom,
            rect_pdf.y0 * self.zoom,
            rect_pdf.x1 * self.zoom,
            rect_pdf.y1 * self.zoom,
        )

    def choose_color(self) -> None:
        result = colorchooser.askcolor(color=self.current_color_hex, title="Elegir color de texto")
        if not result or result[0] is None or result[1] is None:
            return

        (r, g, b), hex_color = result
        self.current_color_rgb = (r / 255.0, g / 255.0, b / 255.0)
        self.current_color_hex = hex_color
        self.color_preview.configure(
            text=hex_color,
            background=hex_color,
            foreground=self.best_text_color_for_background(r, g, b)
        )

    def on_mode_changed(self) -> None:
        self.selected_stamp_index = None
        self.selected_edit_index = None
        self.selected_words.clear()
        self.draw_all_overlays()

        if self.mode_var.get() == "select":
            self.status_var.set("Modo selección: haga clic sobre una palabra o arrastre sobre un bloque de texto.")
        else:
            self.status_var.set("Modo inserción: haga clic en la página para añadir texto nuevo.")

    @staticmethod
    def rgb_tuple_to_hex(rgb: ColorRGB) -> str:
        r, g, b = [max(0, min(255, int(c * 255))) for c in rgb]
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def best_text_color_for_background(r: float, g: float, b: float) -> str:
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return "black" if luminance > 160 else "white"


def main() -> None:
    app = PDFTextEditor()
    app.mainloop()


if __name__ == "__main__":
    main()
