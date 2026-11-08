# Etiquetas de planos

Aplicación en Python y Streamlit para generar etiquetas Code 128 con proyecto,
versión, fecha de entrega y responsable dentro de las barras, además de PNG,
SVG, PDF, CSV y JSON.

## Ejecutar

```sh
pip install -r requirements.txt
streamlit run app.py
```

## Historial

En local se usa SQLite. Para un historial duradero compartido en Streamlit Cloud,
configura `HISTORIAL_GIT_URL` y `HISTORIAL_SSH_KEY` en Secrets. Usa una clave de
escritura limitada a un repositorio privado de historial, que contenga un archivo
`versiones.json` inicializado como `[]`. Nunca subas la clave al repositorio.
Las versiones se guardan mediante commits; un guardado concurrente rechazado se
reintenta con el número actualizado. El historial personal no forma parte del
código público.

Las etiquetas contienen JSON completo y se pueden interpretar sin el historial.
El lector USB escribe esos datos como un teclado. Imprime al 100 % de escala;
la longitud de las barras depende del texto. Los acentos se conservan mediante
escapes JSON reversibles. Verifica la impresión con tu scanner antes de usarla.
