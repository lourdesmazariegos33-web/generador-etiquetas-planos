"""Etiquetas Code 128 con los datos completos, sin identificador externo."""
from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from io import BytesIO, StringIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
if (ROOT / "_vendor").exists():
    sys.path.insert(0, str(ROOT / "_vendor"))

from barcode import Code128
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

FONT = ROOT / "assets" / "DejaVuSansMono.ttf"
if not FONT.exists():
    FONT = ROOT / "DejaVuSansMono.ttf"
pdfmetrics.registerFont(TTFont("Etiqueta", str(FONT)))
HEIGHT = 65.0
MODULE = 0.127  # 3 píxeles exactos a 600 dpi; 5 mil.


def clean(value: str, label: str, limit: int) -> str:
    value = unicodedata.normalize("NFC", " ".join(value.split()))
    if not value:
        raise ValueError(f"Completa el campo {label}.")
    if len(value) > limit:
        raise ValueError(f"{label}: utiliza como máximo {limit} caracteres.")
    if any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError(f"{label}: elimina los caracteres de control.")
    return value


@dataclass(frozen=True)
class Registro:
    proyecto: str
    version: int
    fecha_entrega: str
    responsable: str

    @classmethod
    def crear(cls, proyecto: str, version: str, fecha: date, responsable: str):
        if not isinstance(fecha, date):
            raise ValueError("Selecciona una fecha de entrega válida.")
        if isinstance(version, bool) or not str(version).isdigit() or int(version) < 1:
            raise ValueError("La versión debe ser un número entero positivo.")
        return cls(clean(proyecto, "Proyecto", 80), int(version),
                   fecha.isoformat(), clean(responsable, "Responsable", 80))

    @property
    def codigo(self) -> str:
        # Code 128 es ASCII: JSON escapa los acentos de forma reversible.
        return json.dumps(asdict(self), ensure_ascii=True, separators=(",", ":"))

    @property
    def nombre_archivo(self):
        name = re.sub(r"[^\w.-]+", "_", self.proyecto, flags=re.UNICODE).strip("._")[:50]
        return f"{name or 'proyecto'}_v{self.version}"

    @property
    def ancho(self):
        return max(120.0, len(Code128(self.codigo).build()[0]) * MODULE + 13)

    def datos(self):
        return {**asdict(self), "contenido_barras": self.codigo, "simbologia": "Code 128"}


def lines(text: str, size: float, max_width: float):
    """Ajusta también palabras largas; nunca elimina parte de los datos."""
    result, current = [], ""
    for char in text:
        if pdfmetrics.stringWidth(current + char, "Etiqueta", size) > max_width:
            result.append(current)
            current = char
        else:
            current += char
    if current:
        result.append(current)
    return result


def drawing(registro: Registro):
    """Primitivas comunes en mm para SVG, PNG y PDF; origen superior izquierdo."""
    width = registro.ancho
    texts = [(5, 6, 8, "Etiqueta de proyecto", "#1260CC")]
    for i, line in enumerate(lines("Proyecto: " + registro.proyecto, 9, (width - 10) * mm)):
        texts.append((5, 12 + i * 3.8, 9, line, "#111111"))
    texts.append((5, 22, 8, "Versión: " + str(registro.version), "#111111"))
    texts.append((5, 27, 7, "Entrega: " + date.fromisoformat(registro.fecha_entrega).strftime("%d/%m/%Y"), "#111111"))
    for i, line in enumerate(lines("Responsable: " + registro.responsable, 8, (width - 10) * mm)):
        texts.append((5, 32 + i * 3.3, 7, line, "#111111"))
    bits = Code128(registro.codigo).build()[0]
    x_start = (width - len(bits) * MODULE) / 2
    bars = [(x_start + i * MODULE, 40, MODULE, 15)
            for i, bit in enumerate(bits) if bit == "1"]
    texts.append((5, 60, 7, "Las barras contienen proyecto, versión, fecha de entrega y responsable.", "#111111"))
    return texts, bars


def png(registro: Registro) -> bytes:
    scale = 600 / 25.4
    if registro.ancho > 1000:
        raise ValueError("Los datos producen una etiqueta de más de un metro. Abrevia el proyecto y el responsable.")
    img = Image.new("RGB", (round(registro.ancho * scale), round(HEIGHT * scale)), "white")
    draw = ImageDraw.Draw(img)
    texts, bars = drawing(registro)
    for x, y, w, h in bars:
        left = round(x * scale)
        draw.rectangle((left, round(y * scale), left + 2, round((y + h) * scale) - 1), fill="black")
    for x, y, size, text, color in texts:
        font = ImageFont.truetype(str(FONT), round(size * 600 / 72))
        draw.text((round(x * scale), round(y * scale)), text, font=font, fill=color, anchor="ls")
    out = BytesIO()
    img.save(out, format="PNG", dpi=(600, 600))
    return out.getvalue()


def svg(registro: Registro) -> bytes:
    texts, bars = drawing(registro)
    width = registro.ancho
    elements = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="65mm" viewBox="0 0 {width} 65" role="img"><title>{escape(registro.proyecto)} — versión {registro.version}</title>',
                f'<rect width="{width}" height="65" fill="white"/>']
    elements += [f'<rect x="{x:.4f}" y="{y}" width="{w}" height="{h}" fill="black"/>' for x, y, w, h in bars]
    elements += [f'<text x="{x}" y="{y}" font-family="DejaVu Sans Mono, monospace" font-size="{size * 25.4 / 72:.4f}" fill="{color}" xml:space="preserve">{escape(text)}</text>' for x, y, size, text, color in texts]
    return ("\n".join(elements) + "</svg>").encode("utf-8")


def pdf(registro: Registro, copias: int = 1, hoja: bool = True) -> bytes:
    if not isinstance(copias, int) or not 1 <= copias <= 60:
        raise ValueError("Elige entre 1 y 60 copias.")
    out = BytesIO()
    width = registro.ancho
    if hoja and width > 277:
        raise ValueError(f"La etiqueta mide {width:.0f} mm de ancho y no cabe en A4. Abrevia el proyecto o responsable, o usa el PDF individual a tamaño real.")
    page = landscape(A4) if hoja else (width * mm, HEIGHT * mm)
    canvas = Canvas(out, pagesize=page)
    canvas.setTitle(f"{registro.proyecto} - versión {registro.version}")
    texts, bars = drawing(registro)
    columns = max(1, int((277 + 6) // (width + 6))) if hoja else 1
    per_page = columns * 2
    for i in range(copias if hoja else 1):
        slot = i % per_page if hoja else 0
        if i and slot == 0:
            canvas.showPage()
        ox = (10 + (slot % columns) * (width + 6)) * mm if hoja else 0
        oy = page[1] - ((14 + (slot // columns) * 71 + HEIGHT) * mm) if hoja else 0
        canvas.setFillColorRGB(0, 0, 0)
        for x, y, w, h in bars:
            canvas.rect(ox + x * mm, oy + (HEIGHT - y - h) * mm, w * mm, h * mm, fill=1, stroke=0)
        for x, y, size, text, color in texts:
            canvas.setFillColor(color)
            canvas.setFont("Etiqueta", size)
            canvas.drawString(ox + x * mm, oy + (HEIGHT - y) * mm, text)
        if hoja:
            canvas.setStrokeColorRGB(.8, .84, .88)
            canvas.rect(ox, oy, width * mm, HEIGHT * mm, fill=0, stroke=1)
    canvas.save()
    return out.getvalue()


def exportar(registro: Registro, copias: int):
    data = registro.datos()
    csv_file = StringIO(newline="")
    writer = csv.DictWriter(csv_file, fieldnames=list(data))
    writer.writeheader()
    # Evita que Excel interprete las entradas del usuario como fórmulas.
    writer.writerow({k: "'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v for k, v in data.items()})
    files = {"etiqueta.png": png(registro), "etiqueta.svg": svg(registro),
             "etiqueta.pdf": pdf(registro, hoja=False),
             "datos.json": json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
             "datos.csv": csv_file.getvalue().encode("utf-8-sig")}
    if registro.ancho <= 277:
        files["hoja_A4.pdf"] = pdf(registro, copias)
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(f"{registro.nombre_archivo}/{name}", content)
    return {**files, "todo.zip": archive.getvalue()}


def normalizar_lectura(text: str):
    text = text.strip()
    if text.startswith("]C0"):
        text = text[3:]
    return text


def leer_datos(text: str):
    """Recupera los campos sin historial, sesión ni consulta de base de datos."""
    try:
        value = json.loads(normalizar_lectura(text))
        if not isinstance(value, dict) or set(value) != {"proyecto", "version", "fecha_entrega", "responsable"}:
            raise ValueError("La lectura no contiene los cuatro campos esperados.")
        if not isinstance(value['proyecto'], str) or not isinstance(value['responsable'], str):
            raise ValueError("Proyecto y responsable deben ser texto.")
        return Registro.crear(value['proyecto'], value['version'], date.fromisoformat(value['fecha_entrega']), value['responsable'])
    except (TypeError, KeyError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("No se pudo leer la etiqueta. Escanea el contenido completo de una etiqueta creada con esta versión.") from error
