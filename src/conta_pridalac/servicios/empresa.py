"""Ficha de la empresa y su certificado digital. La contraseña del certificado es la de la empresa: no se guarda en ningún sitio,
sólo se comprueba abriendo el `.pfx` y, mientras dura la sesión, se mantiene en memoria."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from cryptography import x509
from sqlalchemy.orm import Session

from conta_pridalac.db.modelos import Empresa
from conta_pridalac.domain.errores import ErrorContable

CAMPOS_DE_TEXTO = {  # campo → longitud máxima
    "nombre_corto": 32, "carpeta_justificantes": 512, "carpeta_copias": 512, "domicilio": 128, "codigo_postal": 10, "poblacion": 64, "provincia": 32, "pais": 64, "telefono": 32, "email": 128, "web": 128, "iban": 34, "tipo_entidad": 64, "forma_administracion": 64, "codigo_irus": 32, "actividad": 128, "cnae": 8,
    "representante_nombre": 128, "representante_nif": 20, "representante_cargo": 64, "registro_provincia": 32, "registro_tomo": 16, "registro_libro": 16,
    "registro_folio": 16, "registro_hoja": 16, "registro_inscripcion": 16, "is_tipo_gravamen": 15,
    "municipio_ine": 5, "provincia_ine": 2, "presentador_nombre": 64, "presentador_apellido1": 64, "presentador_apellido2": 64, "presentador_nif": 20, "presentador_domicilio": 128,
    "presentador_poblacion": 64, "presentador_cp": 10, "presentador_telefono": 32, "presentador_email": 128,
}


def _nif(valor: str | None) -> str | None:
    valor = re.sub(r"[\s.-]", "", valor or "").upper()
    return valor or None


def modificar_empresa(sesion: Session, empresa: Empresa, nombre: str, *, nif: str | None = None, fecha_constitucion: date | None = None, **ficha) -> Empresa:
    """Guarda la ficha. Los campos de `ficha` que no vienen no se tocan; vacíos se borran."""
    desconocidos = set(ficha) - set(CAMPOS_DE_TEXTO)
    if desconocidos:
        raise ErrorContable(f"Campos de empresa desconocidos: {', '.join(sorted(desconocidos))}")
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorContable("La razón social es obligatoria")
    datos = {c: (ficha[c] or "").strip()[:largo] or None for c, largo in CAMPOS_DE_TEXTO.items() if c in ficha}
    for campo in ("representante_nif",):
        if campo in datos:
            datos[campo] = _nif(datos[campo])
    if datos.get("iban"):
        datos["iban"] = re.sub(r"\s", "", datos["iban"]).upper()
        if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", datos["iban"]):
            raise ErrorContable(f"El IBAN «{datos['iban']}» no tiene un formato válido (por ejemplo ES12 3456 7890 1234 5678 9012)")
    if datos.get("email") and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", datos["email"]):
        raise ErrorContable(f"El correo «{datos['email']}» no parece una dirección válida")
    if datos.get("cnae") and not re.fullmatch(r"\d{4,5}", datos["cnae"]):
        raise ErrorContable("El CNAE son 4 o 5 cifras (por ejemplo 0125)")
    if datos.get("codigo_postal") and not re.fullmatch(r"\d{4,10}", datos["codigo_postal"]):
        raise ErrorContable("El código postal sólo lleva cifras")
    empresa.nombre = nombre[:128]
    empresa.nif = _nif(nif)
    empresa.fecha_constitucion = fecha_constitucion
    for campo, valor in datos.items():
        setattr(empresa, campo, valor)
    sesion.flush()
    return empresa


@dataclass
class InfoCertificado:
    titular: str
    nif: str | None
    caduca: date
    # lo que se deduce del certificado para rellenar la ficha (los certificados españoles no son todos iguales: son propuestas)
    razon_social: str | None = None
    nif_empresa: str | None = None
    representante_nombre: str | None = None
    representante_nif: str | None = None

    @property
    def caducado(self) -> bool:
        return self.caduca < date.today()


def leer_certificado(ruta: str | Path, contrasena: str) -> InfoCertificado:
    """Abre el `.pfx` con su contraseña. Falla con `ErrorContable` si no existe, no es un certificado o la contraseña no es la suya."""
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    ruta = Path(ruta)
    if not ruta.is_file():
        raise ErrorContable(f"No se encuentra el certificado en «{ruta}»")
    try:
        _, certificado, _ = pkcs12.load_key_and_certificates(ruta.read_bytes(), contrasena.encode("utf-8") if contrasena else None)
    except ValueError:
        raise ErrorContable("La contraseña no es la del certificado (o el fichero no es un certificado .pfx válido)") from None
    if certificado is None:
        raise ErrorContable("El fichero no contiene ningún certificado")
    def atributo(oid):
        valores = certificado.subject.get_attributes_for_oid(oid)
        return valores[0].value if valores else None
    serie = atributo(NameOID.SERIAL_NUMBER)
    nif = re.sub(r"^[A-Z]{3,5}[-:]", "", serie).upper() if serie else None
    caduca = getattr(certificado, "not_valid_after_utc", None) or certificado.not_valid_after
    info = InfoCertificado(titular=atributo(NameOID.COMMON_NAME) or atributo(NameOID.ORGANIZATION_NAME) or "", nif=nif, caduca=caduca.date() if isinstance(caduca, datetime) else caduca)
    _deducir_ficha(info, atributo(NameOID.COMMON_NAME), atributo(NameOID.ORGANIZATION_NAME), atributo(x509.ObjectIdentifier("2.5.4.97")), atributo(NameOID.GIVEN_NAME), atributo(NameOID.SURNAME))
    return info


def _deducir_ficha(info: InfoCertificado, cn: str | None, organizacion: str | None, id_organizacion: str | None, nombre: str | None, apellidos: str | None) -> None:
    """Razón social y NIF de la empresa, y nombre y NIF del representante, a partir de los atributos habituales (Verifactu usa las mismas pistas)."""
    es_persona = lambda n: bool(re.fullmatch(r"(\d{8}|[XYZ]\d{7})[A-Z]", n or ""))  # noqa: E731  NIF de persona física o NIE
    es_empresa = lambda n: bool(re.fullmatch(r"[A-HJNP-SUVW]\d{7}[0-9A-J]", n or ""))  # noqa: E731  CIF
    candidatos = []
    if id_organizacion:
        candidatos.append(re.sub(r"^(VAT[A-Z]{2}|[A-Z]{3,5})[-:]?(?=[A-Z0-9]{9}$)", "", id_organizacion.upper()))
    if cn:
        candidatos += [m.upper() for m in re.findall(r"\(R:\s*([A-Z0-9]+)\)", cn, re.I)] + [m.upper() for m in re.findall(r"\bCIF[: ]\s*([A-Z]\d{7}[0-9A-Z])", cn, re.I)]
    if info.nif:
        candidatos.append(info.nif)
    info.nif_empresa = next((c for c in candidatos if es_empresa(c)), None)
    personas = [info.nif] if info.nif else []
    if cn:
        personas += [m.upper() for m in re.findall(r"\bNIF[: ]\s*([A-Z0-9]{9})", cn, re.I)]
    info.representante_nif = next((c for c in personas if es_persona(c)), None)
    if organizacion:
        info.razon_social = organizacion.strip()
    elif cn and info.nif_empresa and re.search(r"\s-\s", cn):
        info.razon_social = cn.split(" - ")[0].strip()
    elif info.nif_empresa and info.nif == info.nif_empresa:
        info.razon_social = info.titular or None  # certificado de la propia sociedad: su nombre común es la razón social
    if nombre or apellidos:
        info.representante_nombre = f"{nombre or ''} {apellidos or ''}".strip().upper() or None
    elif cn and (m := re.search(r"NOMBRE\s+(.+?)\s+-\s+NIF", cn, re.I)):
        info.representante_nombre = m.group(1).strip().upper()


def completar_desde_certificado(empresa: Empresa, info: InfoCertificado) -> list[str]:
    """Rellena de la ficha lo que esté vacío con lo que dice el certificado (nunca pisa lo ya escrito). Devuelve qué campos se han rellenado."""
    rellenados = []
    for campo, valor in (("nombre", info.razon_social), ("nif", info.nif_empresa), ("representante_nombre", info.representante_nombre), ("representante_nif", info.representante_nif)):
        if valor and not (getattr(empresa, campo) or "").strip():
            setattr(empresa, campo, valor)
            rellenados.append(campo)
    return rellenados


# Modelos y trámites que una empresa puede presentar. Cada uno: texto, y las pantallas del menú que le corresponden.
MODELOS = {
    "303": ("303 · IVA (trimestral)", ("modelo-303", "declaraciones", "liquidacion-iva")),
    "390": ("390 · Resumen anual del IVA", ("modelo-390",)),
    "111": ("111 · Retenciones e ingresos a cuenta (trimestral)", ("modelo-111", "declaraciones-111")),
    "115": ("115 · Retenciones por alquileres de locales (trimestral)", ("modelo-115",)),
    "190": ("190 · Resumen anual de retenciones", ("modelo-190", "declaraciones-190")),
    "180": ("180 · Resumen anual de retenciones por alquileres", ("modelo-180",)),
    "347": ("347 · Operaciones con terceros", ("modelo-347", "declaraciones-347")),
    "200": ("200 · Impuesto sobre Sociedades", ("modelo-200",)),
    "202": ("202 · Pago fraccionado del Impuesto sobre Sociedades", ("modelo-202",)),
    "mercantil": ("Registro Mercantil: libros de socios y actas, legalización de libros y depósito de cuentas", ("libro-socios", "libro-actas", "legalizacion-libros", "deposito-cuentas")),
}
MODELOS_POR_PLAN = {"pymes": tuple(MODELOS), "esfl": ("111", "115", "190", "180", "347", "200")}  # lo que se propone al crear la empresa (se puede cambiar en su ficha)
PANTALLA_A_MODELO = {pantalla: codigo for codigo, (_, pantallas) in MODELOS.items() for pantalla in pantallas}


def modelos_de(empresa: Empresa) -> set[str]:
    """Los modelos que presenta la empresa. Las empresas anteriores a esta opción (sin lista) presentan todos."""
    if empresa.modelos is None:
        return set(MODELOS)
    return {m for m in empresa.modelos.split(",") if m in MODELOS}


def fijar_modelos(sesion: Session, empresa: Empresa, codigos) -> None:
    desconocidos = [c for c in codigos if c not in MODELOS]
    if desconocidos:
        raise ErrorContable(f"Modelo desconocido: {', '.join(desconocidos)}")
    empresa.modelos = ",".join(c for c in MODELOS if c in set(codigos))
    sesion.flush()


def modelos_visibles(sesion: Session, empresa: Empresa) -> set[str]:
    """Lo que se enseña en el menú: los modelos que presenta y, aunque ya no los marque, los que tienen presentaciones registradas (para no esconder el historial)."""
    from sqlalchemy import select

    from conta_pridalac.db.modelos import DeclaracionPresentada, PresentacionAeat

    visibles = modelos_de(empresa)
    hechos = set(sesion.scalars(select(PresentacionAeat.modelo).where(PresentacionAeat.empresa_id == empresa.id).distinct()))
    hechos |= set(sesion.scalars(select(DeclaracionPresentada.modelo).where(DeclaracionPresentada.empresa_id == empresa.id).distinct()))
    return visibles | (hechos & set(MODELOS))


PROTECCIONES = {"ninguna": "Sin protección (se abre sin contraseña)", "certificado": "Con certificado digital (.pfx): su contraseña es la de entrada"}


def validar_proteccion(proteccion: str | None) -> str | None:
    if proteccion in (None, ""):
        return None
    if proteccion not in PROTECCIONES:
        raise ErrorContable("La protección de acceso no es válida")
    return proteccion


def fijar_proteccion(sesion: Session, empresa: Empresa, proteccion: str, ruta: str | None, contrasena: str) -> InfoCertificado | None:
    """Cambia la protección de acceso de la empresa. «ninguna» quita el certificado; «certificado» exige uno (el que ya tiene o el que se indique, comprobando su contraseña)."""
    proteccion = validar_proteccion(proteccion)
    ruta = (ruta or "").strip().strip('"')
    if proteccion == "ninguna":
        empresa.certificado_ruta = None
        empresa.proteccion = "ninguna"
        sesion.flush()
        return None
    if proteccion != "certificado":
        raise ErrorContable("Elija cómo se protege la empresa")
    info = None
    if ruta and ruta != (empresa.certificado_ruta or ""):
        info = fijar_certificado(sesion, empresa, ruta, contrasena)
    elif not empresa.certificado_ruta:
        raise ErrorContable("Para proteger la empresa con certificado indique su ruta (.pfx) y su contraseña; o elija «Sin protección»")
    empresa.proteccion = "certificado"
    sesion.flush()
    return info


def fijar_certificado(sesion: Session, empresa: Empresa, ruta: str | None, contrasena: str) -> InfoCertificado | None:
    """Asocia (o quita, con ruta vacía) el certificado de la empresa tras comprobar que la contraseña lo abre."""
    ruta = (ruta or "").strip().strip('"')
    if not ruta:
        empresa.certificado_ruta = None
        sesion.flush()
        return None
    info = leer_certificado(ruta, contrasena)
    empresa.certificado_ruta = str(Path(ruta).resolve())[:512]
    sesion.flush()
    return info
