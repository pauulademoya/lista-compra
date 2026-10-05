"""
Visita la app con un navegador real (no solo un ping HTTP) para que
Streamlit Community Cloud la cuente como una visita de verdad y no la
ponga a dormir. Si la encuentra dormida, pulsa el botón de "despertar" y
espera a que vuelva a estar disponible.
"""
import re
import sys

from playwright.sync_api import sync_playwright

URL = "https://lista-compra-demoyaromero.streamlit.app"
MARCA_APP_VIVA = re.compile(r"lista de la compra", re.IGNORECASE)
POSIBLES_BOTONES_DESPERTAR = [
    re.compile(r"get this app back up", re.IGNORECASE),
    re.compile(r"wake", re.IGNORECASE),
    re.compile(r"yes,", re.IGNORECASE),
]


def app_esta_cargada(page) -> bool:
    for frame in page.frames:
        try:
            texto = frame.inner_text("body")
        except Exception:
            continue
        if MARCA_APP_VIVA.search(texto):
            return True
    return False


def intentar_despertar(page) -> bool:
    for frame in page.frames:
        for patron in POSIBLES_BOTONES_DESPERTAR:
            try:
                boton = frame.get_by_role("button", name=patron)
                if boton.count() > 0:
                    boton.first.click(timeout=5000)
                    return True
            except Exception:
                continue
    return False


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="load", timeout=60000)

        # El contenido real vive en un iframe que puede tardar unos segundos
        # más que el "load" de la página en terminar de cargar.
        for _ in range(6):
            if app_esta_cargada(page):
                print("La app ya estaba despierta, no hace falta hacer nada.")
                browser.close()
                return 0
            page.wait_for_timeout(5000)

        print("La app parece dormida: buscando el botón para despertarla...")
        if intentar_despertar(page):
            pulsado = True
        else:
            pulsado = False

        # Streamlit puede tardar varios minutos en redesplegar el contenedor.
        # Mientras tanto no siempre se ve el botón (a veces solo hay un
        # mensaje de "reiniciando"), así que seguimos recargando y, si en
        # algún momento reaparece el botón, lo volvemos a pulsar.
        for intento in range(18):
            page.wait_for_timeout(15000)
            page.reload(wait_until="load", timeout=60000)
            if app_esta_cargada(page):
                print(f"¡Despertada correctamente! (tras {intento + 1} comprobaciones)")
                browser.close()
                return 0
            if intentar_despertar(page):
                pulsado = True

        print(f"La app no terminó de cargar a tiempo (se pulsó el botón: {pulsado}).")
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
