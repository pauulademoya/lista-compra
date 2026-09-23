import json
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


def _extraer_nombres(datos) -> list[str]:
    # Admite tanto el formato de lista plana como el formato con
    # cantidades/categorías usado brevemente en una versión anterior, para no
    # perder nada de lo que hubiera guardado mientras tanto.
    if isinstance(datos, list):
        return [str(x) for x in datos]
    if isinstance(datos, dict) and isinstance(datos.get("items"), list):
        nombres = []
        for it in datos["items"]:
            if isinstance(it, str):
                nombres.append(it)
            elif isinstance(it, dict) and it.get("nombre"):
                nombres.append(str(it["nombre"]))
        return nombres
    return []


@st.cache_data(ttl=6, show_spinner=False)
def _leer_gist(gist_id: str, token: str) -> list[str]:
    r = _http().get(
        GIST_API.format(id=gist_id),
        headers={"Authorization": f"Bearer {token}"},
        timeout=8,
    )
    r.raise_for_status()
    contenido = r.json()["files"].get("lista.json", {}).get("content", "[]")
    return _extraer_nombres(json.loads(contenido or "[]"))


def cargar_items() -> list[str]:
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
            # Si no se puede leer, paramos: mejor no mostrar (ni machacar) nada.
            st.error("No se pudo cargar la lista. Recarga la página en un momento 🙏")
            st.stop()
    try:
        return _extraer_nombres(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def guardar_items(items: list[str]) -> None:
    contenido = json.dumps(items, ensure_ascii=False, indent=2)
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


def limpiar_widgets(prefijos: tuple[str, ...] = ("sel_", "edit_")) -> None:
    """Borra estados de checkboxes/inputs para que no queden marcas obsoletas."""
    for k in list(st.session_state):
        if k.startswith(prefijos):
            del st.session_state[k]


items = cargar_items()

if "editando" not in st.session_state:
    st.session_state["editando"] = None  # índice del elemento en edición

# ---------- Estilo: limpio, cálido y pensado para el móvil ----------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap');

:root {
    --crema: #f7f4ee;
    --blanco: #ffffff;
    --verde: #5aa871;
    --verde-oscuro: #2f6b46;
    --verde-suave: #e8f3ec;
    --coral: #e8836f;
    --coral-suave: #fdeeea;
    --texto: #3d3a34;
    --gris: #a09a8e;
    --borde: #ece7dd;
}

.stApp, .stApp * { font-family: 'Nunito', 'Segoe UI', sans-serif !important; }
.stApp { background: var(--crema); }

#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
.block-container {
    padding: 1.2rem 1rem 3rem;
    max-width: 680px;
}

/* Cabecera compacta */
.hero {
    text-align: center;
    background: linear-gradient(135deg, var(--verde-suave) 0%, #f3ede0 100%);
    border-radius: 20px;
    padding: 1.2rem 1rem 1.1rem;
    margin-bottom: 1rem;
    border: 1px solid var(--borde);
}
.hero .emoji { font-size: 2.1rem; line-height: 1; }
.hero h1 {
    color: var(--verde-oscuro);
    font-size: 1.45rem;
    font-weight: 800;
    margin: .35rem 0 .1rem;
    padding: 0;
}
.hero p { color: var(--gris); font-size: .88rem; margin: 0; }

/* Tarjetas */
[data-testid="stForm"] {
    background: var(--blanco);
    border: 1px solid var(--borde);
    border-radius: 18px;
    padding: 1rem 1rem .8rem;
    box-shadow: 0 2px 10px rgba(61, 58, 52, .05);
}
[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--blanco);
    border: 1px solid var(--borde) !important;
    border-radius: 16px !important;
    box-shadow: 0 1px 6px rgba(61, 58, 52, .04);
}

/* Filas de la lista: siempre en horizontal, también en móvil */
[class*="st-key-fila"] [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important;
    gap: .45rem !important;
    align-items: center !important;
}
[class*="st-key-fila"] [data-testid="stColumn"] {
    min-width: 0 !important;
    flex: 0 0 auto !important;
    width: auto !important;
}
[class*="st-key-fila"] [data-testid="stColumn"]:nth-child(2) {
    flex: 1 1 auto !important;
    overflow: visible !important;
}
[class*="st-key-fila"] [data-testid="stMarkdownContainer"],
[class*="st-key-fila"] [data-testid="stElementContainer"] {
    overflow: visible !important;
    height: auto !important;
}

.item-text {
    color: var(--texto);
    font-size: 1.02rem;
    font-weight: 600;
    line-height: 1.5;
    padding: .4rem 0;
    overflow-wrap: break-word;
}

.empty-msg {
    text-align: center;
    color: var(--gris);
    background: var(--blanco);
    border: 1.5px dashed var(--borde);
    border-radius: 18px;
    padding: 2rem 1rem;
    font-size: 1rem;
}
.empty-msg .big { font-size: 2rem; display: block; margin-bottom: .4rem; }

/* Inputs: 16px mínimo para que iOS no haga zoom al tocar */
.stTextArea textarea, .stTextInput input {
    background: var(--crema) !important;
    color: var(--texto) !important;
    border: 1.5px solid var(--borde) !important;
    border-radius: 12px !important;
    font-size: 16px !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: var(--verde) !important;
    box-shadow: 0 0 0 3px rgba(90, 168, 113, .15) !important;
}
.stTextArea textarea::placeholder { color: var(--gris) !important; }
[data-testid="stWidgetLabel"] p { color: var(--texto) !important; font-weight: 700; }

/* Botones: tamaño táctil (mínimo 44px) */
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
[data-testid="stBaseButton-secondaryFormSubmit"] {
    background: var(--verde) !important;
    border-color: var(--verde) !important;
    color: #fff !important;
}
[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
    background: var(--verde-oscuro) !important;
    border-color: var(--verde-oscuro) !important;
    color: #fff !important;
}
.stButton > button[kind="primary"] {
    background: var(--coral-suave) !important;
    border-color: var(--coral) !important;
    color: var(--coral) !important;
}
.stButton > button[kind="primary"]:hover {
    background: var(--coral) !important;
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
    min-height: 44px !important;
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

/* Checkbox más grande para el dedo */
.stCheckbox input { accent-color: var(--verde); }
[class*="st-key-fila"] .stCheckbox { padding: .3rem 0; }
[class*="st-key-fila"] .stCheckbox span:first-child { transform: scale(1.25); }

hr { border-color: var(--borde) !important; margin: 1.1rem 0 !important; }

/* Acciones en bloque: apiladas en pantallas pequeñas */
@media (max-width: 640px) {
    .st-key-acciones [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: .5rem !important;
    }
    .st-key-acciones [data-testid="stColumn"] {
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }
}

.counter { text-align: center; margin-top: 1.2rem; }
.counter span {
    display: inline-block;
    background: var(--verde-suave);
    color: var(--verde-oscuro);
    font-weight: 700;
    font-size: .9rem;
    border-radius: 999px;
    padding: .4rem 1.1rem;
}
</style>
""",
    unsafe_allow_html=True,
)

# ---------- Cabecera ----------
st.markdown(
    """
<div class="hero">
    <div class="emoji">🛒</div>
    <h1>Lista de la compra</h1>
    <p>Añade lo que falta en casa y ¡a comprar!</p>
</div>
""",
    unsafe_allow_html=True,
)

# ---------- Añadir elementos ----------
with st.form("form_anadir", clear_on_submit=True):
    nuevos = st.text_area(
        "¿Qué necesitamos?",
        placeholder="Leche, pan, huevos…  (varios separados por comas)",
        height=70,
    )
    if st.form_submit_button("➕  Añadir a la lista", use_container_width=True):
        partes = [
            p.strip()
            for trozo in nuevos.split("\n")
            for p in trozo.split(",")
            if p.strip()
        ]
        if partes:
            items.extend(partes)
            guardar_items(items)
            st.rerun()
        else:
            st.warning("Escribe al menos una cosa 🙂")

st.write("")

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
    seleccionados = []

    for i, item in enumerate(items):
        with st.container(border=True, key=f"fila_{i}"):
            col_check, col_texto, col_editar, col_borrar = st.columns(
                [1, 7, 1, 1], vertical_alignment="center"
            )

            with col_check:
                if st.checkbox(
                    "Seleccionar", key=f"sel_{i}", label_visibility="collapsed"
                ):
                    seleccionados.append(i)

            if st.session_state["editando"] == i:
                with col_texto:
                    nuevo_texto = st.text_input(
                        "Editar elemento",
                        value=item,
                        key=f"edit_{i}",
                        label_visibility="collapsed",
                    )
                with col_editar:
                    if st.button("💾", key=f"guardar_{i}", help="Guardar cambios"):
                        if nuevo_texto.strip():
                            items[i] = nuevo_texto.strip()
                            guardar_items(items)
                        st.session_state["editando"] = None
                        limpiar_widgets(("edit_",))
                        st.rerun()
                with col_borrar:
                    if st.button("✖️", key=f"cancelar_{i}", help="Cancelar"):
                        st.session_state["editando"] = None
                        limpiar_widgets(("edit_",))
                        st.rerun()
            else:
                with col_texto:
                    st.markdown(
                        f'<div class="item-text">{escape(item)}</div>',
                        unsafe_allow_html=True,
                    )
                with col_editar:
                    if st.button("✏️", key=f"editar_{i}", help="Editar"):
                        st.session_state["editando"] = i
                        st.rerun()
                with col_borrar:
                    if st.button("🗑️", key=f"borrar_{i}", help="Eliminar"):
                        items.pop(i)
                        guardar_items(items)
                        st.session_state["editando"] = None
                        limpiar_widgets()
                        st.rerun()

    st.divider()

    # ---------- Enviar por WhatsApp ----------
    texto_lista = "🛒 *Lista de la compra*\n" + "\n".join(f"• {x}" for x in items)
    st.link_button(
        "📲  Enviar por WhatsApp",
        f"https://wa.me/?text={quote(texto_lista)}",
        use_container_width=True,
    )

    # ---------- Acciones en bloque ----------
    with st.container(key="acciones"):
        col_eliminar_sel, col_nueva = st.columns(2)

        with col_eliminar_sel:
            if st.button(
                f"🗑️  Quitar marcados ({len(seleccionados)})",
                disabled=not seleccionados,
                use_container_width=True,
            ):
                restantes = [
                    item for i, item in enumerate(items) if i not in seleccionados
                ]
                guardar_items(restantes)
                st.session_state["editando"] = None
                limpiar_widgets()
                st.rerun()

        with col_nueva:
            if st.button(
                "✨  Empezar lista nueva", type="primary", use_container_width=True
            ):
                guardar_items([])
                st.session_state["editando"] = None
                limpiar_widgets()
                st.rerun()

    n = len(items)
    st.markdown(
        f'<div class="counter"><span>🧺 {n} cosa{"s" if n != 1 else ""} por comprar</span></div>',
        unsafe_allow_html=True,
    )
