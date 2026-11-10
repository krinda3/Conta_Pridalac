"""Dónde están los datos, cómo se cambian de sitio y el candado que impide abrirlos desde dos equipos a la vez."""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from conta_pridalac.domain.errores import ErrorContable
from conta_pridalac.servicios import candado as cd
from conta_pridalac.servicios import ubicacion_datos as ub


def crear_datos(raiz: Path, empresas=("empresa_a", "empresa_b")) -> Path:
    """Una carpeta de datos de verdad: bases SQLite con algo dentro, justificantes y copias."""
    (raiz / "bd").mkdir(parents=True)
    for e in empresas:
        con = sqlite3.connect(raiz / "bd" / f"{e}.sqlite")
        con.execute("create table factura (id integer primary key, total integer)")
        con.executemany("insert into factura(total) values (?)", [(n,) for n in range(50)])
        con.commit()
        con.close()
    (raiz / "bd" / "_preferencias.json").write_text('{"tema": "dark"}', encoding="utf-8")
    (raiz / "justificantes" / "11" / "2025" / "R").mkdir(parents=True)
    (raiz / "justificantes" / "11" / "2025" / "R" / "a.pdf").write_bytes(b"%PDF-1.4 " + os.urandom(2000))
    (raiz / "copias").mkdir()
    (raiz / "copias" / "copia_empresa_a.zip").write_bytes(os.urandom(500))
    return raiz


@pytest.fixture(autouse=True)
def _config_de_prueba(tmp_path, monkeypatch):
    """Nada de estos tests toca la configuración real del usuario ni las variables de entorno del programa."""
    monkeypatch.setenv("CONTA_CONFIG", str(tmp_path / "config"))
    monkeypatch.delenv("CONTA_DATOS", raising=False)


# ------------------------------------------------------------------------------------------------ dónde están los datos

def test_por_defecto_son_los_datos_locales_junto_al_programa():
    bd, origen = ub.resolver()
    assert origen == "por defecto" and bd == ub.RAIZ_PROYECTO / "datos_locales" / "bd"


def test_la_ubicacion_guardada_gana_a_la_de_por_defecto_y_la_variable_a_las_dos(tmp_path, monkeypatch):
    ub.guardar_ubicacion(tmp_path / "otra")
    assert ub.resolver() == ((tmp_path / "otra").resolve() / "bd", "guardada")
    assert not (tmp_path / "otra").exists()                                                       # guardar no crea nada: sólo recuerda
    monkeypatch.setenv("CONTA_DATOS", str(tmp_path / "variable" / "bd"))
    assert ub.resolver() == (tmp_path / "variable" / "bd", "variable")
    ub.guardar_ubicacion(None)
    monkeypatch.delenv("CONTA_DATOS")
    assert ub.resolver()[1] == "por defecto"


def test_un_fichero_de_ubicacion_roto_no_tumba_el_programa(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "ubicacion.json").write_text("esto no es json{", encoding="utf-8")
    assert ub.ubicacion_guardada() is None and ub.resolver()[1] == "por defecto"


def test_inspeccionar_cuenta_empresas_y_tamanos(tmp_path):
    raiz = crear_datos(tmp_path / "datos")
    i = ub.inspeccionar(raiz)
    assert i.tiene_datos and i.empresas == ["empresa_a", "empresa_b"] and i.bytes_justificantes > 2000 and i.bytes_copias == 500 and i.total > 0 and i.problema == ""


def test_inspeccionar_dice_que_pasa_sin_fallar(tmp_path):
    falta = ub.inspeccionar(tmp_path / "no-existe")
    assert not falta.existe and "no está disponible" in falta.problema and not falta.tiene_datos       # un disco desconectado
    (tmp_path / "vacia").mkdir()
    vacia = ub.inspeccionar(tmp_path / "vacia")
    assert vacia.existe and not vacia.tiene_datos and "No hay empresas" in vacia.problema


def test_quien_elige_la_carpeta_bd_en_vez_de_la_raiz_se_corrige(tmp_path):
    raiz = crear_datos(tmp_path / "datos")
    assert ub.normalizar_eleccion(raiz / "bd") == raiz and ub.normalizar_eleccion(f'"{raiz}"') == raiz


def test_usar_otra_carpeta_exige_que_tenga_datos(tmp_path):
    raiz = crear_datos(tmp_path / "datos")
    assert ub.comprobar_destino_para_usar(raiz).tiene_datos
    (tmp_path / "vacia").mkdir()
    with pytest.raises(ErrorContable, match="No hay empresas"):
        ub.comprobar_destino_para_usar(tmp_path / "vacia")
    with pytest.raises(ErrorContable, match="no está disponible"):
        ub.comprobar_destino_para_usar(tmp_path / "desconectada")


# ------------------------------------------------------------------------------------------------ mover los datos

def test_trasladar_copia_verifica_y_deja_el_origen_intacto(tmp_path):
    origen = crear_datos(tmp_path / "origen")
    avisos = []
    informe = ub.trasladar(origen, tmp_path / "nuevo" / "datos", lambda que, hecho, total: avisos.append(que))
    destino = tmp_path / "nuevo" / "datos"
    assert informe.bases == ["empresa_a", "empresa_b"] and informe.ficheros >= 3
    assert ub.inspeccionar(destino).empresas == ["empresa_a", "empresa_b"]
    assert (destino / "justificantes" / "11" / "2025" / "R" / "a.pdf").read_bytes() == (origen / "justificantes" / "11" / "2025" / "R" / "a.pdf").read_bytes()
    assert (destino / "bd" / "_preferencias.json").read_text(encoding="utf-8") == '{"tema": "dark"}'
    assert ub.inspeccionar(origen).empresas == ["empresa_a", "empresa_b"]                                   # el origen sigue ahí…
    assert "nuevo" in (origen / ub.NOTA_DE_TRASLADO).read_text(encoding="utf-8")                        # …con una nota de que se movió
    assert "Verificando la copia" in avisos and avisos[-1] == "Listo"
    con = sqlite3.connect(destino / "bd" / "empresa_a.sqlite")
    assert con.execute("select count(*) from factura").fetchone()[0] == 50
    con.close()


def test_trasladar_una_base_abierta_da_una_copia_coherente(tmp_path):
    origen = crear_datos(tmp_path / "origen")
    abierta = sqlite3.connect(origen / "bd" / "empresa_a.sqlite")                                           # el programa la tiene abierta
    abierta.execute("insert into factura(total) values (999)")
    abierta.commit()
    ub.trasladar(origen, tmp_path / "destino")
    con = sqlite3.connect(tmp_path / "destino" / "bd" / "empresa_a.sqlite")
    assert con.execute("select count(*) from factura").fetchone()[0] == 51
    con.close()
    abierta.close()


def test_el_traslado_no_se_hace_si_no_se_puede_y_dice_por_que(tmp_path):
    origen = crear_datos(tmp_path / "origen")
    with pytest.raises(ErrorContable, match="misma carpeta"):
        ub.trasladar(origen, origen)
    with pytest.raises(ErrorContable, match="dentro"):
        ub.trasladar(origen, origen / "sub")
    with pytest.raises(ErrorContable, match="dentro"):
        ub.trasladar(origen, tmp_path)
    lleno = tmp_path / "lleno"
    lleno.mkdir()
    (lleno / "algo.txt").write_text("x")
    with pytest.raises(ErrorContable, match="no está vacía"):
        ub.trasladar(origen, lleno)
    with pytest.raises(ErrorContable, match="no hay datos que mover"):
        ub.trasladar(tmp_path / "vacio", tmp_path / "d2")
    assert not (origen / ub.NOTA_DE_TRASLADO).exists()                                                 # nada hecho, nada anotado


def test_si_no_cabe_no_empieza(tmp_path, monkeypatch):
    origen = crear_datos(tmp_path / "origen")
    monkeypatch.setattr(ub.shutil, "disk_usage", lambda ruta: type("U", (), {"free": 1024})())
    with pytest.raises(ErrorContable, match="sitio suficiente"):
        ub.trasladar(origen, tmp_path / "destino")
    assert not (tmp_path / "destino").exists()


def test_si_la_copia_sale_mal_se_borra_lo_copiado_y_el_origen_no_se_toca(tmp_path, monkeypatch):
    origen = crear_datos(tmp_path / "origen")
    real = ub.shutil.copy2

    def copia_rota(origen_, destino_, *a, **k):
        real(origen_, destino_, *a, **k)
        Path(destino_).write_bytes(b"corrupto")                                                        # el fichero llega alterado

    monkeypatch.setattr(ub.shutil, "copy2", copia_rota)
    with pytest.raises(ErrorContable, match="no se copió bien"):
        ub.trasladar(origen, tmp_path / "destino")
    assert not (tmp_path / "destino").exists()                                                         # no queda una copia a medias que alguien tome por buena
    assert ub.inspeccionar(origen).empresas == ["empresa_a", "empresa_b"] and not (origen / ub.NOTA_DE_TRASLADO).exists()


def test_los_ficheros_a_medias_no_se_trasladan(tmp_path):
    origen = crear_datos(tmp_path / "origen")
    (origen / "copias" / "copia_x.zip.parcial").write_bytes(b"a medias")
    ub.trasladar(origen, tmp_path / "destino")
    assert not (tmp_path / "destino" / "copias" / "copia_x.zip.parcial").exists()


# ------------------------------------------------------------------------------------------------ el candado

class Reloj:
    def __init__(self):
        self.t = datetime(2026, 11, 8, 10, 0, 0)

    def __call__(self):
        return self.t

    def pasan(self, **tiempo):
        self.t += timedelta(**tiempo)


def candado(raiz, equipo="PORTATIL", pid=100, instancia=None, reloj=None, vivos=()):
    return cd.Candado(raiz, equipo=equipo, usuario="javier", pid=pid, instancia=instancia, ahora=reloj or Reloj(), vivo=lambda p: p in vivos)


def test_sin_candado_se_toma_y_al_cerrar_se_quita(tmp_path):
    c = candado(tmp_path)
    assert c.estado() == (cd.LIBRE, None)
    assert c.adquirir() == (True, None) and c.tengo() and (tmp_path / cd.NOMBRE).exists()
    t = c.titular()
    assert t.equipo == "PORTATIL" and t.usuario == "javier" and t.pid == 100
    c.liberar()
    assert not (tmp_path / cd.NOMBRE).exists() and c.estado() == (cd.LIBRE, None)


def test_otro_equipo_con_el_candado_impide_abrir_y_dice_quien_lo_tiene(tmp_path):
    reloj = Reloj()
    sobremesa = candado(tmp_path, equipo="SOBREMESA", pid=7, reloj=reloj)
    sobremesa.adquirir()
    portatil = candado(tmp_path, equipo="PORTATIL", pid=100, reloj=reloj)
    conseguido, quien = portatil.adquirir()
    assert not conseguido and quien.equipo == "SOBREMESA" and portatil.estado()[0] == cd.OTRO_EQUIPO and not portatil.tengo()
    reloj.pasan(minutes=1)
    assert portatil.en_uso_reciente(quien) and not portatil.posiblemente_pillado(quien) and "SOBREMESA" in quien.describir(reloj())
    reloj.pasan(minutes=30)
    assert not portatil.en_uso_reciente(sobremesa.titular()) and portatil.posiblemente_pillado(sobremesa.titular())
    assert portatil.adquirir()[0] is False                                                             # por vieja que sea la señal, no se toma sola


def test_el_mismo_programa_renueva_su_senal_y_conserva_el_desde(tmp_path):
    reloj = Reloj()
    c = candado(tmp_path, reloj=reloj)
    c.adquirir()
    desde = c.titular().desde
    reloj.pasan(seconds=20)
    assert c.renovar() and c.titular().desde == desde and c.titular().senal != desde


def test_un_candado_huerfano_de_este_equipo_se_toma_solo(tmp_path):
    reloj = Reloj()
    anterior = candado(tmp_path, equipo="PORTATIL", pid=555, reloj=reloj)
    anterior.adquirir()                                                                                # el programa anterior se cerró mal: su proceso ya no existe
    nuevo = candado(tmp_path, equipo="PORTATIL", pid=600, reloj=reloj, vivos=())
    assert nuevo.estado()[0] == cd.HUERFANO
    assert nuevo.adquirir() == (True, None) and nuevo.titular().pid == 600
    vivo = candado(tmp_path, equipo="PORTATIL", pid=700, reloj=reloj, vivos=(600,))                    # pero si el proceso sigue vivo en este equipo, no se le quita
    assert vivo.estado()[0] == cd.OTRO_EQUIPO and vivo.adquirir()[0] is False


def test_forzar_toma_el_control_y_el_antiguo_titular_se_entera(tmp_path):
    reloj = Reloj()
    sobremesa = candado(tmp_path, equipo="SOBREMESA", pid=7, reloj=reloj)
    sobremesa.adquirir()
    portatil = candado(tmp_path, equipo="PORTATIL", pid=100, reloj=reloj)
    portatil.forzar()
    assert portatil.tengo() and portatil.titular().equipo == "PORTATIL"
    assert sobremesa.renovar() is False and not sobremesa.tengo()                                      # el otro, si aún vive, se bloquea al renovar su señal
    sobremesa.liberar()
    assert portatil.tengo()                                                                            # y al cerrarse no le quita el candado al nuevo titular


def test_un_candado_roto_se_trata_como_libre(tmp_path):
    (tmp_path / cd.NOMBRE).write_text("basura{", encoding="utf-8")
    c = candado(tmp_path)
    assert c.estado() == (cd.LIBRE, None) and c.adquirir() == (True, None)


def test_el_proceso_actual_esta_vivo_y_uno_inexistente_no():
    assert cd.proceso_vivo(os.getpid()) and not cd.proceso_vivo(0) and not cd.proceso_vivo(4_000_000)
