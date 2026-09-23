import json
import re
import unicodedata
from html import escape
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st

st.set_page_config(page_title="Lista de la compra", page_icon="🛒", layout="centered")

# ---------- Persistencia ----------
# En tu ordenador la lista se guarda en lista.json. En Streamlit Cloud los
# archivos locales se borran al reiniciarse la app, así que allí se guarda en
# un Gist de GitHub (configurado en los "secrets" de la app).
DATA_FILE = Path(__file__).with_name("lista.json")
GIST_API = "https://api.github.com/gists/{id}"

CATEGORIAS: dict[str, list[str]] = {
    "Fruta y verdura": [
        "platano", "banana", "manzana", "pera", "naranja", "mandarina", "limon",
        "fresa", "tomate", "lechuga", "cebolla", "ajo", "patata", "zanahoria",
        "pepino", "pimiento", "aguacate", "uva", "melon", "sandia", "calabacin",
        "brocoli", "espinaca", "champinon", "kiwi", "melocoton", "ciruela", "piña",
        "apio", "calabaza", "berenjena", "seta",
    ],
    "Carne y pescado": [
        "pollo", "carne", "ternera", "cerdo", "jamon", "chorizo", "salchicha",
        "pescado", "salmon", "atun", "merluza", "gamba", "langostino", "bacon",
        "lomo", "pavo", "costilla", "morcilla", "mejillon", "calamar",
    ],
    "Lácteos y huevos": [
        "leche", "huevo", "yogur", "queso", "nata", "mantequilla", "cuajada",
        "kefir", "natillas", "flan",
    ],
    "Panadería": [
        "pan", "baguette", "bolleria", "croissant", "magdalena", "bollo", "tostada",
        "cruasan",
    ],
    "Bebidas": [
        "agua", "zumo", "refresco", "cerveza", "vino", "cafe", "cacao", "cola",
        "bebida", "te ",
    ],
    "Congelados": ["helado", "congelad", "pizza", "canelones"],
    "Despensa": [
        "arroz", "pasta", "harina", "azucar", "sal", "aceite", "lenteja",
        "garbanzo", "conserva", "cereales", "galleta", "chocolate", "miel",
        "especia", "mermelada", "salsa", "mayonesa", "ketchup", "macarrones",
        "sopa", "caldo",
    ],
    "Limpieza y hogar": [
        "lejia", "detergente", "suavizante", "papel higienico", "servilleta",
        "bolsa de basura", "estropajo", "fregasuelos", "friegasuelos", "fregona",
        "guante",
    ],
    "Higiene y cuidado personal": [
        "champu", "gel de baño", "pasta de dientes", "desodorante", "jabon",
        "compresa", "cepillo de dientes", "colonia", "crema",
    ],
}
ORDEN_CATEGORIAS = list(CATEGORIAS) + ["Otros"]


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_acentos.lower().strip()


def categorizar(nombre: str) -> str:
    n = _normalizar(nombre)
    for categoria, claves in CATEGORIAS.items():
        if any(clave in n for clave in claves):
            return categoria
    return "Otros"


def _capitalizar(texto: str) -> str:
    texto = texto.strip()
    return texto[:1].upper() + texto[1:] if texto else texto


def _parsear_item(texto: str) -> dict:
    m = re.match(r"^(.+?)\s*[x×]\s*(\d{1,3})$", texto.strip(), re.IGNORECASE)
    if m:
        return {"nombre": _capitalizar(m.group(1)), "cantidad": f"x{m.group(2)}", "comprado": False}
    return {"nombre": _capitalizar(texto), "cantidad": None, "comprado": False}


def _gist_config() -> tuple[str, str] | None:
    try:
        return st.secrets["gist"]["id"], st.secrets["gist"]["token"]
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def _http() -> requests.Session:
    # Una sesión reutilizada entre recargas: evita repetir el apretón de manos
    # TLS con GitHub en cada interacción.
    return requests.Session()


def _normalizar_datos(datos) -> dict:
    if isinstance(datos, list):
        # Formato antiguo: lista plana de nombres (sin cantidad ni categoría).
        items = [{"nombre": str(x), "cantidad": None, "comprado": False} for x in datos]
        return {"items": items, "frecuencia": {}}
    if not isinstance(datos, dict):
        return {"items": [], "frecuencia": {}}
    items_ok = []
    for it in datos.get("items", []):
        if isinstance(it, str):
            items_ok.append({"nombre": it, "cantidad": None, "comprado": False})
        elif isinstance(it, dict) and it.get("nombre"):
            items_ok.append(
                {
                    "nombre": str(it["nombre"]),
                    "cantidad": it.get("cantidad"),
                    "comprado": bool(it.get("comprado", False)),
                }
            )
    frecuencia = datos.get("frecuencia")
    return {"items": items_ok, "frecuencia": frecuencia if isinstance(frecuencia, dict) else {}}


@st.cache_data(ttl=6, show_spinner=False)
def _leer_gist(gist_id: str, token: str) -> dict:
    r = _http().get(
        GIST_API.format(id=gist_id),
        headers={"Authorization": f"Bearer {token}"},
        timeout=8,
    )
    r.raise_for_status()
    contenido = r.json()["files"].get("lista.json", {}).get("content", "{}")
    return _normalizar_datos(json.loads(contenido or "{}"))


def cargar_datos() -> dict:
    cfg = _gist_config()
    if cfg:
        gist_id, token = cfg
        try:
            # En caché unos segundos: así marcar una casilla o teclear no
            # dispara una petición de red en cada rerun de Streamlit.
            return _leer_gist(gist_id, token)
        except requests.exceptions.HTTPError as e:
            codigo = e.response.status_code if e.response is not None else "?"
            st.error(f"No se pudo cargar la lista (código {codigo}). Recarga la página en un momento 🙏")
            st.stop()
        except Exception:
            st.error("No se pudo cargar la lista. Recarga la página en un momento 🙏")
            st.stop()
    try:
        return _normalizar_datos(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"items": [], "frecuencia": {}}


def guardar_datos(datos: dict) -> None:
    contenido = json.dumps(datos, ensure_ascii=False, indent=2)
    cfg = _gist_config()
    if cfg:
        gist_id, token = cfg
        try:
            r = _http().patch(
                GIST_API.format(id=gist_id),
                headers={"Authorization": f"Bearer {token}"},
                json={"files": {"lista.json": {"content": contenido}}},
                timeout=8,
            )
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            codigo = e.response.status_code if e.response is not None else "?"
            st.error(f"No se pudo guardar el cambio (código {codigo}). Inténtalo de nuevo 🙏")
            st.stop()
        except Exception:
            st.error("No se pudo guardar el cambio. Inténtalo de nuevo 🙏")
            st.stop()
        # Invalida la caché: la próxima lectura (en este u otro dispositivo)
        # debe ver ya el cambio, no la versión anterior servida en caché.
        _leer_gist.clear()
    else:
        DATA_FILE.write_text(contenido, encoding="utf-8")


def registrar_frecuencia(frecuencia: dict, nombre: str) -> None:
    clave = _normalizar(nombre)
    entrada = frecuencia.get(clave, {"nombre": nombre, "n": 0})
    entrada["nombre"] = nombre
    entrada["n"] = entrada.get("n", 0) + 1
    frecuencia[clave] = entrada


def limpiar_widgets(prefijos: tuple[str, ...] = ("chk_",)) -> None:
    """Borra estados de checkboxes para que no queden marcas obsoletas tras
    añadir o eliminar elementos (los índices de las filas cambian)."""
    for k in list(st.session_state):
        if k.startswith(prefijos):
            del st.session_state[k]


datos = cargar_datos()
items = datos["items"]
frecuencia = datos["frecuencia"]

# ---------- Estilo: limpio, cálido y pensado para el móvil ----------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');

:root {
    --pagina: #ece7dd;
    --blanco: #ffffff;
    --verde: #5aa871;
    --verde-oscuro: #2f6b46;
    --verde-suave: #e8f3ec;
    --coral: #e8836f;
    --texto: #3d3a34;
    --gris: #a09a8e;
    --borde: #ece7dd;
}

.stApp, .stApp * { font-family: 'Nunito', 'Segoe UI', sans-serif !important; }
.stApp { background: var(--pagina); }

#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
.block-container {
    background: var(--blanco);
    border-radius: 26px;
    box-shadow: 0 10px 34px rgba(61, 58, 52, .12);
    padding: 1.4rem 1.2rem 2rem;
    margin-top: 1.3rem;
    max-width: 480px;
}

/* Cabecera */
.titulo { color: var(--texto); font-size: 1.35rem; font-weight: 800; }
.subtitulo { color: var(--gris); font-size: .85rem; margin-top: .1rem; }

/* Menú "..." */
[data-testid="stPopover"] > button {
    border-radius: 50% !important;
    width: 2.3rem !important;
    height: 2.3rem !important;
    padding: 0 !important;
    border: 1px solid var(--borde) !important;
    background: var(--blanco) !important;
    color: var(--texto) !important;
    font-weight: 800 !important;
}

/* Sugerencias */
.sugerencias-label {
    color: var(--gris);
    font-size: .82rem;
    font-weight: 700;
    margin: .9rem 0 .4rem;
}

/* Categorías */
.categoria-label {
    color: var(--gris);
    font-size: .74rem;
    font-weight: 800;
    letter-spacing: .06em;
    margin: 1.1rem 0 .4rem .2rem;
}

/* Tarjetas de fila */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--blanco);
    border: 1px solid var(--borde) !important;
    border-radius: 14px !important;
    box-shadow: 0 1px 5px rgba(61, 58, 52, .04);
    margin-bottom: .4rem;
}

.item-text {
    color: var(--texto);
    font-size: 1rem;
    font-weight: 600;
    line-height: 1.5;
    padding: .3rem 0;
    overflow-wrap: break-word;
}
.item-text.comprado {
    color: var(--gris);
    text-decoration: line-through;
}
.qty-badge {
    display: inline-block;
    background: var(--verde-suave);
    color: var(--verde-oscuro);
    font-size: .72rem;
    font-weight: 700;
    border-radius: 999px;
    padding: .05rem .5rem;
    margin-left: .35rem;
}

/* Carrito */
.carrito-label {
    color: var(--gris);
    font-size: .74rem;
    font-weight: 800;
    letter-spacing: .06em;
    padding-top: .5rem;
}

.empty-msg {
    text-align: center;
    color: var(--gris);
    background: var(--blanco);
    border: 1.5px dashed var(--borde);
    border-radius: 18px;
    padding: 2rem 1rem;
    font-size: 1rem;
    margin-top: .5rem;
}
.empty-msg .big { font-size: 2rem; display: block; margin-bottom: .4rem; }
.todo-listo {
    text-align: center;
    color: var(--verde-oscuro);
    font-weight: 700;
    padding: 1rem;
}

/* Inputs: 16px mínimo para que iOS no haga zoom al tocar */
.stTextInput input, .stTextArea textarea {
    background: var(--pagina) !important;
    color: var(--texto) !important;
    border: 1.5px solid var(--borde) !important;
    border-radius: 12px !important;
    font-size: 16px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: var(--verde) !important;
    box-shadow: 0 0 0 3px rgba(90, 168, 113, .15) !important;
}
.stTextInput input::placeholder { color: var(--gris) !important; }

/* Botones */
.stButton > button, [data-testid="stBaseButton-secondaryFormSubmit"] {
    border-radius: 999px !important;
    font-weight: 700 !important;
    border: 1.5px solid var(--borde) !important;
    background: var(--blanco) !important;
    color: var(--texto) !important;
    min-height: 44px !important;
    transition: all .12s ease;
}
.stButton > button:hover, [data-testid="stBaseButton-secondaryFormSubmit"]:hover {
    border-color: var(--verde) !important;
    background: var(--verde-suave) !important;
    color: var(--verde-oscuro) !important;
}
/* Botón "+" de añadir: verde relleno y circular */
[data-testid="stBaseButton-secondaryFormSubmit"] {
    background: var(--verde) !important;
    border-color: var(--verde) !important;
    color: #fff !important;
    border-radius: 50% !important;
    width: 44px !important;
    padding: 0 !important;
}
[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
    background: var(--verde-oscuro) !important;
    border-color: var(--verde-oscuro) !important;
    color: #fff !important;
}
.stButton > button:disabled {
    opacity: .45;
    background: var(--blanco) !important;
    color: var(--gris) !important;
    border-color: var(--borde) !important;
}
/* Botón-enlace de WhatsApp */
.stLinkButton a {
    border-radius: 999px !important;
    font-weight: 700 !important;
    min-height: 46px !important;
    background: #25d366 !important;
    border: 1.5px solid #25d366 !important;
    color: #fff !important;
    transition: all .12s ease;
}
.stLinkButton a:hover {
    background: #1eb457 !important;
    border-color: #1eb457 !important;
    color: #fff !important;
}

.stCheckbox input { accent-color: var(--verde); }
hr { border-color: var(--borde) !important; margin: 1rem 0 !important; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------- Cabecera ----------
pendientes_total = sum(1 for it in items if not it["comprado"])
col_titulo, col_menu = st.columns([5, 1], vertical_alignment="center")
with col_titulo:
    st.markdown(
        f'<div class="titulo">Lista de la compra</div>'
        f'<div class="subtitulo">{pendientes_total} cosa{"s" if pendientes_total != 1 else ""} por comprar</div>',
        unsafe_allow_html=True,
    )
with col_menu:
    with st.popover("⋯", use_container_width=True):
        if st.button("🆕 Empezar lista nueva", use_container_width=True):
            datos["items"] = []
            guardar_datos(datos)
            limpiar_widgets()
            st.rerun()

st.write("")

# ---------- Añadir elementos ----------
with st.form("form_anadir", clear_on_submit=True):
    col_input, col_boton = st.columns([6, 1], vertical_alignment="center")
    with col_input:
        nuevos = st.text_input(
            "Añadir",
            placeholder="Añadir… (leche, huevos x12)",
            label_visibility="collapsed",
        )
    with col_boton:
        enviado = st.form_submit_button("➕", use_container_width=True)
    if enviado:
        partes = [
            p.strip()
            for trozo in nuevos.split("\n")
            for p in trozo.split(",")
            if p.strip()
        ]
        if partes:
            for parte in partes:
                nuevo = _parsear_item(parte)
                items.append(nuevo)
                registrar_frecuencia(frecuencia, nuevo["nombre"])
            guardar_datos(datos)
            st.rerun()
        else:
            st.warning("Escribe al menos una cosa 🙂")

# ---------- Sugerencias: "Sueles comprar" ----------
nombres_activos = {_normalizar(it["nombre"]) for it in items}
sugerencias = sorted(
    (v for k, v in frecuencia.items() if k not in nombres_activos),
    key=lambda v: -v.get("n", 0),
)[:4]
if sugerencias:
    st.markdown('<div class="sugerencias-label">Sueles comprar:</div>', unsafe_allow_html=True)
    cols = st.columns(len(sugerencias))
    for col, sug in zip(cols, sugerencias):
        with col:
            if st.button(f"+ {sug['nombre']}", key=f"sug_{sug['nombre']}"):
                items.append({"nombre": sug["nombre"], "cantidad": None, "comprado": False})
                registrar_frecuencia(frecuencia, sug["nombre"])
                guardar_datos(datos)
                st.rerun()


def _fila(indice: int, item: dict) -> None:
    with st.container(border=True, key=f"fila_{indice}"):
        col_chk, col_txt, col_trash = st.columns([1, 7, 1], vertical_alignment="center")
        with col_chk:
            marcado = st.checkbox(
                "Comprado", value=item["comprado"], key=f"chk_{indice}", label_visibility="collapsed"
            )
            if marcado != item["comprado"]:
                items[indice]["comprado"] = marcado
                guardar_datos(datos)
                limpiar_widgets()
                st.rerun()
        with col_txt:
            cantidad_html = (
                f'<span class="qty-badge">{escape(item["cantidad"])}</span>' if item["cantidad"] else ""
            )
            clase = "item-text comprado" if item["comprado"] else "item-text"
            st.markdown(
                f'<div class="{clase}">{escape(item["nombre"])}{cantidad_html}</div>',
                unsafe_allow_html=True,
            )
        with col_trash:
            if st.button("🗑️", key=f"del_{indice}", help="Eliminar"):
                items.pop(indice)
                guardar_datos(datos)
                limpiar_widgets()
                st.rerun()


# ---------- Lista de elementos ----------
if not items:
    st.markdown(
        """
<div class="empty-msg">
    <span class="big">🧺</span>
    La cesta está vacía.<br>Añade lo primero que se te ocurra ✨
</div>
""",
        unsafe_allow_html=True,
    )
else:
    pendientes_idx = [(i, it) for i, it in enumerate(items) if not it["comprado"]]
    carrito_idx = [(i, it) for i, it in enumerate(items) if it["comprado"]]

    grupos: dict[str, list[tuple[int, dict]]] = {}
    for i, it in pendientes_idx:
        grupos.setdefault(categorizar(it["nombre"]), []).append((i, it))

    if pendientes_idx:
        for categoria in ORDEN_CATEGORIAS:
            if categoria not in grupos:
                continue
            st.markdown(f'<div class="categoria-label">{categoria.upper()}</div>', unsafe_allow_html=True)
            for i, it in grupos[categoria]:
                _fila(i, it)
    elif carrito_idx:
        st.markdown('<div class="todo-listo">🎉 ¡Todo listo!</div>', unsafe_allow_html=True)

    if carrito_idx:
        col_label, col_quitar = st.columns([3, 1], vertical_alignment="center")
        with col_label:
            st.markdown(
                f'<div class="carrito-label">EN EL CARRO · {len(carrito_idx)}</div>',
                unsafe_allow_html=True,
            )
        with col_quitar:
            if st.button("Quitar", key="quitar_carrito", use_container_width=True):
                datos["items"] = [it for it in items if not it["comprado"]]
                guardar_datos(datos)
                limpiar_widgets()
                st.rerun()
        for i, it in carrito_idx:
            _fila(i, it)

    if pendientes_idx:
        st.write("")
        lineas = []
        for categoria in ORDEN_CATEGORIAS:
            if categoria not in grupos:
                continue
            lineas.append(f"*{categoria.upper()}*")
            for _, it in grupos[categoria]:
                cantidad = f" {it['cantidad']}" if it["cantidad"] else ""
                lineas.append(f"• {it['nombre']}{cantidad}")
        texto_lista = "🛒 *Lista de la compra*\n" + "\n".join(lineas)
        st.link_button(
            "📲  Enviar por WhatsApp",
            f"https://wa.me/?text={quote(texto_lista)}",
            use_container_width=True,
        )
