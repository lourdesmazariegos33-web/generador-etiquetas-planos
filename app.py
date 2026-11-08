"""Etiquetas de planos con datos completos y versiones persistentes."""
from datetime import datetime, date
import json
import sqlite3
from zoneinfo import ZoneInfo
import streamlit as st
from etiquetas import Registro, exportar, leer_datos
from historial import siguiente, generar_y_guardar, listar, permanente

st.set_page_config(page_title="Etiquetas de planos", page_icon=":material/barcode:", layout="wide")
today = datetime.now(ZoneInfo("America/Guatemala")).date()
defaults = {"proyecto": "", "fecha": today, "responsable": "", "copias": 2,
            "resultado": None, "lectura": ""}
for key, value in defaults.items():
    st.session_state.setdefault(key, value)
# Descarta resultados anteriores al formato de datos completos.
if st.session_state.resultado and not isinstance(st.session_state.resultado[0].version, int):
    st.session_state.resultado = None


def limpiar():
    st.session_state.update(defaults)


st.title("Etiquetas de planos", anchor=False)
st.write("Guarda cada versión de tu proyecto y lleva sus datos dentro del código de barras.")
form_col, preview_col = st.columns([1, 1.2], gap="large")
with form_col:
    with st.container(border=True):
        st.subheader("Datos del proyecto", anchor=False)
        st.text_input("Proyecto", key="proyecto", max_chars=80, placeholder="Ej. z11",
                      help="Escribe el mismo nombre para continuar sus versiones. Presiona Enter o sal del campo para actualizar la versión.")
        try:
            next_version, db_ok = siguiente(st.session_state.proyecto), True
        except (sqlite3.Error, OSError):
            next_version, db_ok = 1, False
            st.error("No se puede acceder al historial. Revisa su conexión y configuración antes de generar.")
        c1, c2 = st.columns([1, 1.2])
        c1.text_input("Próxima versión", value=str(next_version), disabled=True)
        c2.date_input("Fecha de entrega", key="fecha", format="DD/MM/YYYY")
        if st.session_state.proyecto.strip():
            st.caption(f"Se guardará la versión {next_version}." if next_version == 1 else
                       f"Última versión guardada: {next_version - 1}. La siguiente será la {next_version}.")
        st.text_input("Responsable", key="responsable", max_chars=80, placeholder="Nombre y apellido")
        st.number_input("Copias en el PDF A4", key="copias", min_value=1, max_value=60,
                        step=1, help="La distribución depende del ancho real de las barras.")
        if st.button("Generar y guardar versión", type="primary", width="stretch",
                     icon=":material/barcode:", disabled=not db_ok):
            try:
                with st.spinner("Generando archivos y guardando la versión…"):
                    record, files = generar_y_guardar(st.session_state.proyecto,
                        st.session_state.fecha, st.session_state.responsable,
                        int(st.session_state.copias), exportar)
                st.session_state.resultado = (record, int(st.session_state.copias), files)
                st.session_state.lectura = ""
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except (sqlite3.Error, OSError):
                st.error("No se pudo guardar esta versión. No se reservó ningún número; revisa el acceso a la carpeta datos.")
        st.caption("Cada generación guarda una nueva versión. Volver a descargar una versión guardada no cambia su número.")
        st.button("Limpiar formulario", on_click=limpiar, width="stretch")

with preview_col:
    with st.container(border=True):
        st.subheader("Tu etiqueta", anchor=False)
        result = st.session_state.resultado
        if result:
            record, copies, files = result
            if (st.session_state.proyecto.strip() != record.proyecto or
                st.session_state.responsable.strip() != record.responsable or
                st.session_state.fecha.isoformat() != record.fecha_entrega or st.session_state.copias != copies):
                st.info("La vista previa corresponde a la versión guardada. Genera para guardar los nuevos datos en la siguiente versión.")
            st.success(f"{record.proyecto} · Versión {record.version} guardada")
            st.image(files["etiqueta.png"], width="stretch", alt=f"Etiqueta de {record.proyecto}, versión {record.version}, con sus datos completos en Code 128")
            st.caption(f"Tamaño real: {record.ancho:.1f} × 65 mm · PNG a 600 dpi · Code 128")
            if 'hoja_A4.pdf' not in files:
                st.warning(f"Las barras requieren {record.ancho:.0f} mm de ancho. No caben en A4: usa el PDF individual a tamaño real, un plano grande o abrevia los nombres al crear otra versión. No reduzcas la etiqueta.")
            st.subheader("Esto leerá el scanner", anchor=False)
            st.code(record.codigo, language="json", wrap_lines=True)
            st.caption("Los cuatro datos están en las barras. No necesitas consultar el historial para interpretarlos. Los acentos se conservan como escapes JSON: por ejemplo \\u00ed equivale a í.")
            st.download_button("Descargar todos los formatos", files["todo.zip"], record.nombre_archivo + ".zip",
                               mime="application/zip", width="stretch", on_click="ignore", icon=":material/download:")
            with st.container(horizontal=True):
                for name, label, mime in [
                    ("etiqueta.png", "Imagen PNG", "image/png"),
                    ("etiqueta.svg", "Vector SVG", "image/svg+xml"),
                    ("etiqueta.pdf", "PDF individual", "application/pdf"),
                    ("hoja_A4.pdf", "PDF A4", "application/pdf"),
                    ("datos.csv", "Datos CSV", "text/csv"),
                    ("datos.json", "Datos JSON", "application/json")]:
                    if name in files:
                        st.download_button(label, files[name], record.nombre_archivo + "_" + name, mime=mime, on_click="ignore")
        else:
            st.info("Escribe el proyecto y completa los datos. La versión se asigna al guardar.")
            st.write("Por ejemplo, el scanner entregará este texto:")
            st.code(Registro.crear("z11", 2, today, "Ana López").codigo, language="json", wrap_lines=True)
            st.write("Podrás leer el proyecto, su versión, la fecha de entrega y quién es responsable, sin buscar un identificador.")

with st.expander("Leer una etiqueta y ver sus datos", icon=":material/usb:", expanded=True):
    st.write("Haz clic en el campo y escanea una etiqueta. Funciona aunque el proyecto no esté guardado en esta computadora. El scanner actúa como un teclado; también puedes escanear en un editor de texto.")
    scanned = st.text_input("Lectura del scanner", key="lectura", placeholder="Haz clic aquí antes de escanear")
    if scanned:
        try:
            read = leer_datos(scanned)
            st.success("Datos recuperados de las barras")
            st.write(f"**Proyecto:** {read.proyecto}")
            st.write(f"**Versión:** {read.version}")
            st.write(f"**Fecha de entrega:** {date.fromisoformat(read.fecha_entrega).strftime('%d/%m/%Y')}")
            st.write(f"**Responsable:** {read.responsable}")
        except ValueError as error:
            st.error(str(error))

with st.expander("Versiones guardadas y respaldo", icon=":material/history:"):
    try:
        history = listar()
        if history:
            st.dataframe(history, hide_index=True, width="stretch")
            choice = st.selectbox("Recuperar una versión para descargar", range(len(history)),
                                 format_func=lambda i: f"{history[i]['proyecto']} · versión {history[i]['version']} · {history[i]['fecha_entrega']}")
            if st.button("Abrir versión guardada"):
                item = history[choice]
                saved = Registro.crear(item['proyecto'], item['version'], date.fromisoformat(item['fecha_entrega']), item['responsable'])
                st.session_state.resultado = (saved, int(st.session_state.copias), exportar(saved, int(st.session_state.copias)))
                st.rerun()
            st.download_button("Respaldar historial JSON", json.dumps(history, ensure_ascii=False, indent=2).encode('utf-8'),
                               'historial_proyectos.json', mime='application/json', on_click='ignore')
        else:
            st.write("Todavía no hay versiones guardadas.")
    except (sqlite3.Error, OSError):
        st.error("No se pudo abrir el historial.")
    if permanente():
        st.caption("El historial se guarda de forma permanente en un repositorio privado y se comparte entre computadoras. Limpiar el formulario no lo borra.")
    else:
        st.caption("El historial se guarda en datos/proyectos.sqlite3. En una instalación local conserva esa carpeta al mover la aplicación. En un alojamiento temporal puede perderse al reiniciar; configura el historial permanente antes de usar numeraciones definitivas. Limpiar el formulario no borra el historial.")

with st.expander("Impresión y compatibilidad", icon=":material/print:"):
    st.markdown("""
    - **PNG:** 600 dpi. **SVG y PDF:** barras vectoriales.
    - **PDF individual:** ancho calculado con los datos, altura de 65 mm.
    - **PDF A4:** orientación horizontal, disponible cuando la etiqueta cabe al tamaño real.
    - Imprime al **100 %**, sin ajustar a página. No recortes las zonas blancas laterales.
    - Cuanto más texto, más anchas las barras. Usa nombres breves; el programa conserva todos los datos sin sustituirlos por un identificador.
    - El SAT LI102N+ es un lector 1D: conservar Code 128 exige una etiqueta más ancha que un QR. Verifica una impresión con tu scanner antes de repetirla en los planos.
    - Los acentos se conservan en JSON ASCII. Aquí se muestran de nuevo como texto normal. La distribución de teclado del scanner debe coincidir con la computadora para transmitir comillas y llaves.
    """)
st.caption("Etiquetas de planos · Datos completos en Code 128 · " + ("Historial permanente compartido" if permanente() else "Historial local de versiones"))
