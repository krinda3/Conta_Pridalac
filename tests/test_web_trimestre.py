"""El asistente del trimestre: los pasos en orden, con su estado, y el enlace a la pantalla de cada uno."""
from sqlalchemy import select

from conta_pridalac.db.modelos import Empresa, PresentacionAeat
from test_web_extractos import _sesion, cliente, importar  # noqa: F401 - `cliente` es una fixture

BASE = "/e/prueba/2026/trimestre"


def test_el_menu_ofrece_el_trimestre_el_primero(cliente):
    inicio = cliente.get("/e/prueba/2026").text
    assert f'href="{BASE}"' in inicio and inicio.index(f'href="{BASE}"') < inicio.index("/facturas-recibidas")


def test_la_pantalla_enseña_los_dieciseis_pasos_con_su_estado(cliente):
    tabla = cliente.get(f"{BASE}/tabla").text
    for titulo in ("Importar los extractos del trimestre", "Cargar las facturas recibidas", "Quitar las duplicadas de Verifactu", "Aplicar las propuestas con extracto", "Contabilizar el resto como pendientes de pago", "Cargar y aplicar las facturas emitidas",
                   "Enlazar el extracto con lo ya contabilizado", "Decidir las líneas sin factura", "Comprobar que cada banco cuadra con su Mayor", "Pasar la auditoría de integridad", "Presentar el modelo 303", "Presentar el modelo 111"):
        assert titulo in tabla
    assert "No hay ninguna cargada" in tabla and "Sin presentar" in tabla and "pasos hechos" in tabla


def test_un_paso_se_abre_con_su_enlace_a_la_pantalla(cliente):
    assert 'href="/e/prueba/2026/extractos"' in cliente.get(f"{BASE}/f/1").text
    paso = cliente.get(f"{BASE}/f/2").text
    assert "Paso 2" in paso and "Cargar las facturas recibidas" in paso and 'href="/e/prueba/2026/conciliacion"' in paso
    cliente.post(f"{BASE}/accion/cambiar", data={"trimestre": "2026-1"})
    assert 'href="/e/prueba/2026/auditoria"' in cliente.get(f"{BASE}/f/14").text  # la auditoría va antes de presentar los modelos
    assert 'href="/e/prueba/2026/modelo-303?abrir=1"' in cliente.get(f"{BASE}/f/15").text  # los modelos abren el trimestre elegido
    assert 'href="/e/prueba/2026/emitidas-trimestre"' in cliente.get(f"{BASE}/f/10").text
    assert cliente.get(f"{BASE}/f/99").status_code == 404


def test_el_menu_junta_el_proceso_del_cierre_en_la_caja_trimestre(cliente):
    inicio = cliente.get("/e/prueba/2026").text
    for nombre in ("extractos", "conciliacion", "emitidas-trimestre", "conciliar-pagos", "lineas-sin-factura", "cuadre-bancos", "correspondencias"):
        assert f'href="/e/prueba/2026/{nombre}"' in inicio
    assert inicio.index('href="/e/prueba/2026/extractos"') < inicio.index('href="/e/prueba/2026/movimientos"')  # los del cierre van en la caja Trimestre, antes que Tesorería


def test_los_pasos_se_ordenan_como_numeros(cliente):
    tabla = cliente.get(f"{BASE}/tabla?orden=numero&dir=desc").text
    assert tabla.index("Presentar el modelo 111") < tabla.index("Cargar las facturas recibidas") < tabla.index("Importar los extractos del trimestre")  # 15, 2, 1 y no «9, 8… 10, 1»


def test_copiar_los_justificantes_de_hacienda_a_la_carpeta_de_la_empresa(cliente, tmp_path):
    cliente.post(f"{BASE}/accion/cambiar", data={"trimestre": "2026-1"})
    assert "Sin configurar" in cliente.get(f"{BASE}/tabla").text
    assert "no tiene configurada la carpeta" in cliente.get(f"{BASE}/accion/copiar").text
    almacen = cliente.app.state.config.almacen
    pdf = b"%PDF-1.4 justificante"
    (almacen / "aeat").mkdir(parents=True, exist_ok=True)
    (almacen / "aeat" / "1_justificante.pdf").write_bytes(pdf)
    s = _sesion(cliente)
    empresa = s.scalars(select(Empresa)).first()
    empresa.nombre_corto, empresa.carpeta_justificantes = "PRUEBA", str(tmp_path / "OneDrive" / "Hacienda {año}")
    s.add(PresentacionAeat(empresa_id=empresa.id, modelo="303", anio=2026, periodo="1T", estado="presentada", respuesta_ruta="aeat/1_justificante.pdf"))
    (almacen / "aeat" / "2_justificante.pdf").write_bytes(b"%PDF-1.4 otro trimestre")
    s.add(PresentacionAeat(empresa_id=empresa.id, modelo="303", anio=2026, periodo="2T", estado="presentada", respuesta_ruta="aeat/2_justificante.pdf"))  # de otro trimestre: no se toca
    s.commit()
    s.close()
    assert "1 de 1 justificantes sin copiar" in cliente.get(f"{BASE}/tabla").text
    previo = cliente.get(f"{BASE}/accion/copiar").text
    assert "PRUEBA AEAT Mod 303 1T 2026.pdf" in previo and "Se copiará" in previo and "Mod 303 2T 2026" not in previo and "del 1T 2026" in previo
    assert not (tmp_path / "OneDrive").exists()  # ver no copia
    hecho = cliente.post(f"{BASE}/accion/copiar").text
    assert "Justificantes copiados" in hecho and "Copiados</span><strong>1<" in hecho
    assert (tmp_path / "OneDrive" / "Hacienda 2026" / "PRUEBA AEAT Mod 303 1T 2026.pdf").read_bytes() == pdf
    assert not (tmp_path / "OneDrive" / "Hacienda 2026" / "PRUEBA AEAT Mod 303 2T 2026.pdf").exists()  # los de los demás trimestres ya estaban donde estaban
    assert "1 justificantes copiados" in cliente.get(f"{BASE}/tabla").text
    assert "Ya está copiado" in cliente.get(f"{BASE}/accion/copiar").text  # repetir no crea nada nuevo


def test_sin_datos_de_partida_los_pasos_no_se_dan_por_hechos(cliente):
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Sin datos" in tabla and "Todavía no hay facturas recibidas cargadas del trimestre" in tabla and "Todavía no hay extractos importados del trimestre" in tabla
    assert "Ninguna duplicada pendiente" not in tabla and "Todos los proveedores están decididos" not in tabla  # nada que revisar no es lo mismo que nada empezado


def test_se_elige_el_trimestre_de_trabajo_y_se_ve_en_las_pantallas(cliente):
    assert "Cambiar de trimestre" in cliente.get(BASE).text
    dialogo = cliente.get(f"{BASE}/accion/cambiar").text
    assert '<option value="2026-1"' in dialogo and '<option value="2026-4"' in dialogo and dialogo.count("<option") == 4  # sólo los cuatro trimestres del año abierto
    assert "Elija un trimestre de la lista" in cliente.post(f"{BASE}/accion/cambiar", data={"trimestre": "2026-9"}).text
    hecho = cliente.post(f"{BASE}/accion/cambiar", data={"trimestre": "2026-2"}).text
    assert "Trabajando en 2T 2026" in hecho
    for pantalla in ("trimestre", "conciliacion", "emitidas-trimestre", "lineas-sin-factura", "conciliar-pagos"):
        assert "Trabajando en 2T 2026" in cliente.get(f"/e/prueba/2026/{pantalla}").text and "cambiar de trimestre" in cliente.get(f"/e/prueba/2026/{pantalla}").text
    assert "Trabajando en" not in cliente.get("/e/prueba/2026/movimientos").text  # las demás pantallas no trabajan por trimestre
    sesion = _sesion(cliente)
    sesion.scalars(select(Empresa)).first().trimestre_trabajo = "2025-4"
    sesion.commit()
    sesion.close()
    assert "tiene abierto el ejercicio 2026" in cliente.get(f"{BASE}/tabla").text  # otro año que el del ejercicio abierto: se avisa en vez de mezclar


def test_los_pasos_sin_configurar_llevan_a_la_ficha_de_la_empresa(cliente):
    tabla = cliente.get(f"{BASE}/tabla").text
    assert "Sin configurar" in tabla
    for numero in (17, 18):  # la copia de los justificantes y la copia de seguridad, sin carpeta
        paso = cliente.get(f"{BASE}/f/{numero}")
        assert paso.status_code == 200
    assert 'href="/empresa/prueba"' in cliente.get(f"{BASE}/f/18").text
    assert cliente.get("/empresa/prueba").status_code == 200  # y esa dirección existe
