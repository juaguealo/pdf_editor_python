# Editor de texto para PDF con Python - versión 2

Esta versión permite añadir texto nuevo y, además, seleccionar texto existente para borrarlo, sustituirlo o modificar su apariencia.

## 1. Instalación con Conda

```bash
conda create -n pdfeditor python=3.11
conda activate pdfeditor
pip install -r requirements.txt
```

## 2. Ejecución

```bash
python pdf_text_editor.py
```

## 3. Funciones disponibles

### Añadir texto nuevo

1. Seleccione el modo **Añadir texto nuevo**.
2. Escriba el texto.
3. Configure tamaño, fuente y color.
4. Haga clic sobre la página del PDF.

### Seleccionar texto existente

1. Seleccione el modo **Seleccionar texto existente**.
2. Haga clic sobre una palabra o arrastre un rectángulo sobre una línea o bloque.
3. El texto detectado se copiará al cuadro de edición.

### Borrar texto existente

1. Seleccione el texto existente.
2. Pulse **Borrar seleccionado**.
3. La operación se aplicará al guardar el PDF.

### Sustituir texto existente

1. Seleccione el texto existente.
2. Escriba el nuevo texto en el cuadro de edición.
3. Configure tamaño, fuente y color.
4. Pulse **Sustituir seleccionado**.
5. Guarde el PDF.

### Cambiar características manteniendo el mismo contenido

1. Seleccione el texto existente.
2. Configure tamaño, fuente y color.
3. Pulse **Cambiar estilo manteniendo texto**.
4. Guarde el PDF.

## 4. Nota técnica importante

Un PDF no es equivalente a un documento Word. Su contenido suele estar formado por instrucciones de dibujo, texto posicionado, fuentes y recursos gráficos. Por ello, esta aplicación no modifica directamente el flujo textual original. La edición se realiza con una estrategia robusta:

1. detectar las palabras existentes;
2. crear una redacción sobre el área seleccionada;
3. insertar opcionalmente nuevo texto encima.

Esto permite borrar o sustituir texto de forma práctica, aunque la maquetación perfecta dependerá del diseño del PDF original.

## 5. Dependencias

- PyMuPDF
- Pillow
- Tkinter, incluido normalmente con Python/Conda
