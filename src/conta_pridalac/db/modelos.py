"""Esquema objetivo v0.

Alcance de esta versión: empresa y ejercicio, plan de cuentas, terceros, asientos y apuntes, facturas con
IVA/ajustes/adjuntos y bienes de inversión. **Tesorería** (bancos, vencimientos, cobros y pagos) queda para el
Hito 1, cuando esté leído el pseudocódigo de `Vtos`/`ListaPagos`.

Decisiones:
- Importes en céntimos enteros (`Dinero`), nunca `float`.
- Subcuentas de `Empresa.digitos_cuenta` dígitos (8 por defecto). El código MGD (7 dígitos) se convierte a 8 sólo en Empresa A y Empresa B (`migracion.cuentas`); el resto de empresas conserva los suyos.
- Un asiento se identifica por `(ejercicio, tipo, numero, sub)` igual que en el programa anterior (`2.194`); `numero_diario`
  es la numeración correlativa del libro diario (la de MGD `ASIENTO`) y puede ser nula hasta que se asigne.
- Un asiento debe cuadrar (Σ debe = Σ haber). SQLite no puede comprobarlo por fila, así que se exige en el
  servicio que graba y se audita con `db.integridad.asientos_descuadrados`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from conta_pridalac.db.tipos import Dinero


class Base(DeclarativeBase):
    pass


# Tipos de asiento (identificador `tipo.numero`, como la columna Serie del programa anterior)
TIPO_EMITIDAS = 1
TIPO_RECIBIDAS = 2
TIPO_TESORERIA = 3
TIPO_GENERAL = 4
TIPO_AUTOMATICO = 9
TIPOS_ASIENTO = (TIPO_EMITIDAS, TIPO_RECIBIDAS, TIPO_TESORERIA, TIPO_GENERAL, TIPO_AUTOMATICO)


class Empresa(Base):
    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[int] = mapped_column(Integer, unique=True)  # nº de empresa en MGD (011, 012)
    nombre: Mapped[str] = mapped_column(String(128))
    nif: Mapped[str | None] = mapped_column(String(20))
    nombre_corto: Mapped[str | None] = mapped_column(String(32))  # prefijo de los nombres de fichero que se preparan para presentar (vacío = la razón social sin S.L.)
    # ficha de la empresa (envíos a la AEAT, depósito de cuentas y libros del Registro Mercantil)
    domicilio: Mapped[str | None] = mapped_column(String(128))
    codigo_postal: Mapped[str | None] = mapped_column(String(10))
    poblacion: Mapped[str | None] = mapped_column(String(64))
    provincia: Mapped[str | None] = mapped_column(String(32))
    pais: Mapped[str | None] = mapped_column(String(64))
    telefono: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(128))
    web: Mapped[str | None] = mapped_column(String(128))
    iban: Mapped[str | None] = mapped_column(String(34))  # cuenta bancaria de la empresa
    actividad: Mapped[str | None] = mapped_column(String(128))
    cnae: Mapped[str | None] = mapped_column(String(8))
    fecha_constitucion: Mapped[date | None] = mapped_column(Date)
    representante_nombre: Mapped[str | None] = mapped_column(String(128))
    representante_nif: Mapped[str | None] = mapped_column(String(20))
    representante_cargo: Mapped[str | None] = mapped_column(String(64))
    registro_provincia: Mapped[str | None] = mapped_column(String(32))
    registro_tomo: Mapped[str | None] = mapped_column(String(16))
    registro_libro: Mapped[str | None] = mapped_column(String(16))
    registro_folio: Mapped[str | None] = mapped_column(String(16))
    registro_hoja: Mapped[str | None] = mapped_column(String(16))
    registro_inscripcion: Mapped[str | None] = mapped_column(String(16))
    # certificado digital: sólo la ruta del .pfx (fuera del repositorio); su contraseña nunca se guarda
    tipo_entidad: Mapped[str | None] = mapped_column(String(64))  # Sociedad limitada…
    forma_administracion: Mapped[str | None] = mapped_column(String(64))  # Administrador único, administradores solidarios…
    codigo_irus: Mapped[str | None] = mapped_column(String(32))  # identificador único de la inscripción en el Registro Mercantil
    certificado_ruta: Mapped[str | None] = mapped_column(String(512))
    # cómo se protege la entrada a la empresa: «certificado» (la contraseña de su .pfx), «ninguna» (se abre sin contraseña) o nulo (empresas anteriores: se decide como antes, por la ruta del certificado)
    proteccion: Mapped[str | None] = mapped_column(String(12))
    # modelos y trámites que presenta la empresa, separados por comas (`303,111,347`…): sólo de ésos salen plazos, pasos del trimestre y opciones de menú. Nulo = todos (empresas anteriores).
    modelos: Mapped[str | None] = mapped_column(String(80))
    carpeta_justificantes: Mapped[str | None] = mapped_column(String(512))  # dónde se copian los PDF de Hacienda de los modelos presentados (D:\OneDrive\EMPRESA\Hacienda {año}); vacío = no se copian
    carpeta_copias: Mapped[str | None] = mapped_column(String(512))  # dónde se lleva la copia de seguridad del final del trimestre (OneDrive…); vacío = no se lleva
    trimestre_trabajo: Mapped[str | None] = mapped_column(String(7))  # «2026-4»: el trimestre con el que se trabaja el cierre; todas las pantallas del trimestre se limitan a sus fechas (vacío = el de la factura más reciente de la lista)
    tipo_plan: Mapped[str] = mapped_column(String(8), default="pymes", server_default="pymes")  # plan de cuentas: «pymes» (PGC de empresas) o «esfl» (entidades sin fines lucrativos)
    is_tipo_gravamen: Mapped[str | None] = mapped_column(String(15))  # tipo de gravamen del IS del ejercicio en curso, tal como va en el 202 («25»); vacío = 25
    is_cifra_menor_1m: Mapped[bool] = mapped_column(default=True, server_default="1")  # cifra de negocios del periodo anterior inferior a un millón de euros (marca del 202)
    # legalización de libros en el Registro Mercantil (datos de la ficha que pide Legalia2): el municipio y la provincia (códigos del INE) y quien presenta
    municipio_ine: Mapped[str | None] = mapped_column(String(5))
    provincia_ine: Mapped[str | None] = mapped_column(String(2))
    presentador_nombre: Mapped[str | None] = mapped_column(String(64))
    presentador_apellido1: Mapped[str | None] = mapped_column(String(64))
    presentador_apellido2: Mapped[str | None] = mapped_column(String(64))
    presentador_nif: Mapped[str | None] = mapped_column(String(20))
    presentador_domicilio: Mapped[str | None] = mapped_column(String(128))
    presentador_poblacion: Mapped[str | None] = mapped_column(String(64))
    presentador_cp: Mapped[str | None] = mapped_column(String(10))
    presentador_telefono: Mapped[str | None] = mapped_column(String(32))
    presentador_email: Mapped[str | None] = mapped_column(String(128))
    digitos_cuenta: Mapped[int] = mapped_column(Integer, default=8, server_default="8")  # dígitos de las subcuentas: se fija al crear la empresa (las de MGD, los suyos; las del programa anterior, 8)

    ejercicios: Mapped[list[Ejercicio]] = relationship(back_populates="empresa")
    actividades: Mapped[list[ActividadEmpresa]] = relationship(back_populates="empresa", order_by="ActividadEmpresa.orden", cascade="all, delete-orphan")
    representantes: Mapped[list[RepresentanteEmpresa]] = relationship(back_populates="empresa", order_by="RepresentanteEmpresa.orden", cascade="all, delete-orphan")


class ActividadEmpresa(Base):
    """Actividad de la empresa para los datos estadísticos del 390; la de `orden` 0 es la principal."""

    __tablename__ = "empresa_actividad"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    descripcion: Mapped[str] = mapped_column(String(40))
    codigo: Mapped[str | None] = mapped_column(String(3))  # código de actividad del modelo 390 (A03, B04…)
    epigrafe: Mapped[str | None] = mapped_column(String(4))  # epígrafe del IAE

    empresa: Mapped[Empresa] = relationship(back_populates="actividades")


class RepresentanteEmpresa(Base):
    """Representante con poder de una persona jurídica (el 390 admite hasta tres)."""

    __tablename__ = "empresa_representante"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    nombre: Mapped[str] = mapped_column(String(80))
    nif: Mapped[str | None] = mapped_column(String(9))
    fecha_poder: Mapped[date | None] = mapped_column(Date)
    notaria: Mapped[str | None] = mapped_column(String(12))

    empresa: Mapped[Empresa] = relationship(back_populates="representantes")


class Ejercicio(Base):
    __tablename__ = "ejercicio"
    __table_args__ = (
        UniqueConstraint("empresa_id", "anio"),
        CheckConstraint("fecha_fin >= fecha_inicio"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    anio: Mapped[int] = mapped_column(Integer)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date] = mapped_column(Date)
    cerrado: Mapped[bool] = mapped_column(default=False)

    empresa: Mapped[Empresa] = relationship(back_populates="ejercicios")


class Cuenta(Base):
    """Cuenta del plan. Solo las subcuentas, las que tienen los `digitos_cuenta` de la empresa, admiten apuntes."""

    __tablename__ = "cuenta"
    __table_args__ = (
        UniqueConstraint("empresa_id", "codigo"),
        CheckConstraint("length(codigo) BETWEEN 1 AND 12"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    codigo: Mapped[str] = mapped_column(String(12))
    nombre: Mapped[str] = mapped_column(String(128))

    @property
    def es_subcuenta(self) -> bool:
        from sqlalchemy.orm import object_session

        sesion = object_session(self)
        empresa = sesion.get(Empresa, self.empresa_id) if sesion is not None else None
        return len(self.codigo) == (empresa.digitos_cuenta if empresa is not None else 8)


class Tercero(Base):
    """Cliente, proveedor, acreedor o deudor (comparten ficha, como en MGD)."""

    __tablename__ = "tercero"
    __table_args__ = (Index("ix_tercero_empresa_nif", "empresa_id", "nif"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    clase: Mapped[str] = mapped_column(String(1))  # C cliente · P proveedor
    numero_origen: Mapped[int | None] = mapped_column(Integer)  # nº en MGD (Clientes.NUMERO / Proveed.NUMERO)
    nombre: Mapped[str] = mapped_column(String(128))
    comercial: Mapped[str | None] = mapped_column(String(64))
    nif: Mapped[str | None] = mapped_column(String(20))
    cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    cuenta_irpf_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))  # Proveed.CTAIRPF

    # ---- datos de la ficha (los de la pantalla de clientes y proveedores del programa anterior)
    tipo_identificador: Mapped[str | None] = mapped_column(String(32))  # NIF, NIF-IVA, pasaporte…
    domicilio: Mapped[str | None] = mapped_column(String(128))
    codigo_postal: Mapped[str | None] = mapped_column(String(10))
    poblacion: Mapped[str | None] = mapped_column(String(64))
    provincia: Mapped[str | None] = mapped_column(String(32))
    pais: Mapped[str | None] = mapped_column(String(64))
    telefonos: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(128))
    web: Mapped[str | None] = mapped_column(String(128))
    observaciones: Mapped[str | None] = mapped_column(Text)
    divisa: Mapped[str | None] = mapped_column(String(3))
    recargo_equivalencia: Mapped[bool] = mapped_column(default=False)
    no_incluir_347: Mapped[bool] = mapped_column(default=False)  # MGD DECLTERC
    generico: Mapped[bool] = mapped_column(default=False)  # proveedor o cliente genérico
    criterio_caja: Mapped[bool] = mapped_column(default=False)  # MGD CCAJA
    reagp: Mapped[bool] = mapped_column(default=False)  # régimen especial de agricultura, ganadería y pesca
    provincia_190: Mapped[str | None] = mapped_column(String(2))  # modelo 190: código de provincia del perceptor (28 Madrid, 13 Ciudad Real…)
    clave_190: Mapped[str | None] = mapped_column(String(1))  # modelo 190: clave de percepción (G, H, I…)
    subclave_190: Mapped[str | None] = mapped_column(String(2))  # modelo 190: subclave de percepción (dos cifras)
    # modelo 180: inmueble que alquila el arrendador (un inmueble por proveedor; el diseño pide estos datos en cada registro de perceptor)
    inmueble_situacion: Mapped[str | None] = mapped_column(String(1))  # 1 con referencia catastral (resto de España) · 2 País Vasco · 3 Navarra · 4 sin referencia catastral
    inmueble_catastro: Mapped[str | None] = mapped_column(String(20))
    inmueble_tipo_via: Mapped[str | None] = mapped_column(String(5))  # CL, AV, PZ…
    inmueble_via: Mapped[str | None] = mapped_column(String(50))
    inmueble_tipo_numeracion: Mapped[str | None] = mapped_column(String(3))  # NUM, KM, S/N
    inmueble_numero: Mapped[str | None] = mapped_column(String(5))
    inmueble_calificador: Mapped[str | None] = mapped_column(String(3))  # BIS, DUP…
    inmueble_bloque: Mapped[str | None] = mapped_column(String(3))
    inmueble_portal: Mapped[str | None] = mapped_column(String(3))
    inmueble_escalera: Mapped[str | None] = mapped_column(String(3))
    inmueble_planta: Mapped[str | None] = mapped_column(String(3))
    inmueble_puerta: Mapped[str | None] = mapped_column(String(3))
    inmueble_complemento: Mapped[str | None] = mapped_column(String(40))
    inmueble_localidad: Mapped[str | None] = mapped_column(String(30))
    inmueble_municipio: Mapped[str | None] = mapped_column(String(30))
    inmueble_codigo_municipio: Mapped[str | None] = mapped_column(String(5))  # código INE
    inmueble_provincia: Mapped[str | None] = mapped_column(String(2))
    inmueble_codigo_postal: Mapped[str | None] = mapped_column(String(5))
    # por defecto en las facturas del tercero
    cuenta_gasto_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))  # subcuenta de gasto (proveedor) o de ingreso (cliente)
    cuenta_suplidos_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    tipos_iva_defecto: Mapped[str | None] = mapped_column(String(16))  # números de tipo de IVA separados por comas (hasta tres)
    retencion_pct: Mapped[Decimal | None] = mapped_column(Dinero)
    pct_iva_deducible: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("100.00"))
    tipo_operacion: Mapped[str | None] = mapped_column(String(64))
    tipo_exencion_iva: Mapped[str | None] = mapped_column(String(64))  # clientes
    # datos de pago o de cobro
    pago_directo: Mapped[bool] = mapped_column(default=False)  # cobro o pago directo en la factura
    cuenta_pago_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))  # subcuenta de pago o de cobro por defecto
    forma_pago_id: Mapped[int | None] = mapped_column(ForeignKey("forma_pago.id"))
    iban: Mapped[str | None] = mapped_column(String(34))
    bic: Mapped[str | None] = mapped_column(String(11))


class Asiento(Base):
    __tablename__ = "asiento"
    __table_args__ = (
        UniqueConstraint("ejercicio_id", "tipo", "numero", "sub"),
        Index("ix_asiento_ejercicio_fecha", "ejercicio_id", "fecha"),
        Index("ix_asiento_numero_diario", "ejercicio_id", "numero_diario"),
        CheckConstraint("tipo IN (1,2,3,4,9)"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ejercicio_id: Mapped[int] = mapped_column(ForeignKey("ejercicio.id"))
    tipo: Mapped[int] = mapped_column(Integer)
    numero: Mapped[int] = mapped_column(Integer)  # nº dentro de (ejercicio, tipo)
    sub: Mapped[int] = mapped_column(Integer, default=0)  # asientos adicionales de una misma factura (MGD MULTI)
    numero_diario: Mapped[int | None] = mapped_column(Integer)  # correlativo del libro diario
    fecha: Mapped[date] = mapped_column(Date)
    concepto: Mapped[str] = mapped_column(String(255), default="")
    subtipo: Mapped[str | None] = mapped_column(String(1))  # MGD TPASIENTO: M, A apertura, P IVA, R regul., Z cierre

    apuntes: Mapped[list[Apunte]] = relationship(
        back_populates="asiento", order_by="Apunte.orden", cascade="all, delete-orphan"
    )

    @property
    def identificador(self) -> str:
        return f"{self.tipo}.{self.numero}" + (f"/{self.sub}" if self.sub else "")


class Apunte(Base):
    __tablename__ = "apunte"
    __table_args__ = (
        CheckConstraint("debe >= 0 AND haber >= 0", name="ck_apunte_signo"),
        CheckConstraint("NOT (debe > 0 AND haber > 0)", name="ck_apunte_un_lado"),
        Index("ix_apunte_cuenta", "cuenta_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asiento_id: Mapped[int] = mapped_column(ForeignKey("asiento.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("cuenta.id"))
    debe: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    haber: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    concepto: Mapped[str | None] = mapped_column(String(255))
    documento: Mapped[str | None] = mapped_column(String(40))

    asiento: Mapped[Asiento] = relationship(back_populates="apuntes")
    cuenta: Mapped[Cuenta] = relationship()


class Factura(Base):
    """Factura recibida (`R`) o emitida (`E`)."""

    __tablename__ = "factura"
    __table_args__ = (
        UniqueConstraint("ejercicio_id", "sentido", "numero"),
        CheckConstraint("sentido IN ('E','R')"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ejercicio_id: Mapped[int] = mapped_column(ForeignKey("ejercicio.id"))
    sentido: Mapped[str] = mapped_column(String(1))
    numero: Mapped[int] = mapped_column(Integer)  # nº de documento (el programa anterior `2_194`, MGD Rec.NUMERO)
    fecha_contable: Mapped[date] = mapped_column(Date)  # fecha de introducción (determina el periodo)
    fecha_factura: Mapped[date | None] = mapped_column(Date)
    numero_factura: Mapped[str | None] = mapped_column(String(40))  # nº del proveedor / serie emitida
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))
    cuenta_tercero_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    cuenta_contrapartida_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))  # gasto o ingreso
    # categoría de análisis del gasto (informe «Gastos por categoría»): no es contable, no cambia ningún asiento y se puede fijar aunque el ejercicio esté cerrado.
    # Nula = se deduce de la cuenta de gasto (ver `servicios/categorias_gasto.py`).
    categoria_gasto_id: Mapped[int | None] = mapped_column(ForeignKey("categoria_gasto.id"))
    total: Mapped[Decimal] = mapped_column(Dinero)
    concepto: Mapped[str | None] = mapped_column(String(255))
    notas: Mapped[str | None] = mapped_column(Text)

    tercero: Mapped[Tercero | None] = relationship()
    cuenta_tercero: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_tercero_id])
    cuenta_contrapartida: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_contrapartida_id])
    ivas: Mapped[list[FacturaIva]] = relationship(back_populates="factura", cascade="all, delete-orphan")
    ajustes: Mapped[list[FacturaAjuste]] = relationship(back_populates="factura", cascade="all, delete-orphan")
    adjuntos: Mapped[list[Adjunto]] = relationship(back_populates="factura", cascade="all, delete-orphan")


class CategoriaGasto(Base):
    """Categoría para analizar el gasto de una empresa (gas, electricidad, combustible, abonos, labores…). Es una etiqueta de análisis, no una cuenta.

    `cuentas`: prefijos de cuenta, separados por comas, cuyo gasto cae en esta categoría cuando la factura no tiene otra asignada (p. ej. `62800002` o `68`).
    Así, las cuentas nuevas que se abran desde 2026 enlazan solas con su categoría y no hay dos sistemas.
    """

    __tablename__ = "categoria_gasto"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    codigo: Mapped[str] = mapped_column(String(40))
    nombre: Mapped[str] = mapped_column(String(128))
    tipo: Mapped[str] = mapped_column(String(16), default="gasto")  # gasto · inversion · amortizacion · impuesto · excepcional · financiero
    cuentas: Mapped[str | None] = mapped_column(String(255))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    cuenta_destino: Mapped[str | None] = mapped_column(String(12))  # subcuenta a la que van las facturas de esta categoría desde que se llevan con cuentas con sentido (2026 en adelante)
    amortizacion_anos: Mapped[int | None] = mapped_column(Integer)  # solo informativo: años de amortización teórica para ver el coste neto en el informe (no se contabiliza)


class FacturaReparto(Base):
    """Parte de una factura que va a una categoría distinta de la principal (p. ej. la tienda de una gasolinera → comidas). `importe` es la base de esa parte."""

    __tablename__ = "factura_reparto"

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("factura.id", ondelete="CASCADE"))
    categoria_gasto_id: Mapped[int] = mapped_column(ForeignKey("categoria_gasto.id"))
    importe: Mapped[Decimal] = mapped_column(Dinero)
    nota: Mapped[str | None] = mapped_column(String(255))


class FacturaIva(Base):
    """Una fila por tipo de IVA de la factura."""

    __tablename__ = "factura_iva"

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("factura.id", ondelete="CASCADE"))
    base: Mapped[Decimal] = mapped_column(Dinero)
    pct_iva: Mapped[Decimal] = mapped_column(Dinero)  # 21,00 → guardado en céntimos de punto
    cuota_iva: Mapped[Decimal] = mapped_column(Dinero)
    cuenta_iva_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    pct_recargo: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    cuota_recargo: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    cuenta_recargo_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    deducible: Mapped[bool] = mapped_column(default=True)  # MGD NODEDU = "S" → False
    bien_inversion: Mapped[bool] = mapped_column(default=False)

    cuenta_iva: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_iva_id])
    cuenta_recargo: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_recargo_id])
    factura: Mapped[Factura] = relationship(back_populates="ivas")


class FacturaAjuste(Base):
    """Línea extra sobre la factura (IRPF, retenciones, suplidos…). MGD tabla `Ajustes`."""

    __tablename__ = "factura_ajuste"

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(ForeignKey("factura.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    cuenta_id: Mapped[int] = mapped_column(ForeignKey("cuenta.id"))
    importe: Mapped[Decimal] = mapped_column(Dinero)
    contra: Mapped[str] = mapped_column(String(1))  # C cliente · I ingreso · G gasto · P proveedor
    cambio_asiento: Mapped[bool] = mapped_column(default=False)
    afecta_iva: Mapped[bool] = mapped_column(default=False)
    declaracion_terceros: Mapped[bool] = mapped_column(default=False)

    cuenta: Mapped[Cuenta] = relationship()
    factura: Mapped[Factura] = relationship(back_populates="ajustes")


class Adjunto(Base):
    """PDF o JPG (justificante) de una factura, de un movimiento de banco o de un asiento.

    El fichero vive en disco; aquí solo la referencia y la huella. Cuelga de **exactamente uno** de los tres
    documentos. `sha256` y `tamano` nulos = el fichero referenciado no está en disco (la auditoría lo avisa).
    """

    __tablename__ = "adjunto"
    __table_args__ = (
        CheckConstraint("tipo_mime IN ('application/pdf','image/jpeg')"),
        CheckConstraint(
            "(factura_id IS NOT NULL) + (movimiento_banco_id IS NOT NULL) + (asiento_id IS NOT NULL) = 1",
            name="ck_adjunto_un_origen",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int | None] = mapped_column(ForeignKey("factura.id", ondelete="CASCADE"))
    movimiento_banco_id: Mapped[int | None] = mapped_column(ForeignKey("movimiento_banco.id", ondelete="CASCADE"))
    asiento_id: Mapped[int | None] = mapped_column(ForeignKey("asiento.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    nombre: Mapped[str] = mapped_column(String(255))
    ruta_relativa: Mapped[str] = mapped_column(String(512))
    tipo_mime: Mapped[str] = mapped_column(String(40))
    sha256: Mapped[str | None] = mapped_column(String(64))
    tamano: Mapped[int | None] = mapped_column(Integer)

    factura: Mapped[Factura | None] = relationship(back_populates="adjuntos")

    @property
    def presente(self) -> bool:
        return self.sha256 is not None


class BienInversion(Base):
    """Ficha de inmovilizado (campos de la pantalla "Elementos de inmovilizado" del programa anterior)."""

    __tablename__ = "bien_inversion"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    codigo: Mapped[int] = mapped_column(Integer)
    descripcion: Mapped[str] = mapped_column(String(128))
    tipo_elemento: Mapped[str | None] = mapped_column(String(64))
    clasificacion: Mapped[str | None] = mapped_column(String(32))
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id"))
    numero_factura_compra: Mapped[str | None] = mapped_column(String(40))
    fecha_adquisicion: Mapped[date | None] = mapped_column(Date)
    fecha_funcionamiento: Mapped[date | None] = mapped_column(Date)
    precio_compra: Mapped[Decimal] = mapped_column(Dinero)
    valor_residual: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    valor_suelo: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    nuevo: Mapped[bool] = mapped_column(default=True)
    metodo: Mapped[str] = mapped_column(String(16), default="lineal")
    periodicidad: Mapped[str] = mapped_column(String(16), default="anual")
    porcentaje_anual: Mapped[Decimal | None] = mapped_column(Dinero)
    cuenta_inmovilizado_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    cuenta_amortizacion_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    cuenta_dotacion_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    fecha_baja: Mapped[date | None] = mapped_column(Date)
    causa_baja: Mapped[str | None] = mapped_column(String(64))
    no_amortizar_en_baja: Mapped[bool] = mapped_column(default=False)

    # Datos del cuadro (MGD Lbi.PERIODO/MESES/COEFI) para poder regenerarlo
    periodos_vida: Mapped[int | None] = mapped_column(Integer)
    meses_periodo: Mapped[int] = mapped_column(Integer, default=12)
    coeficiente_pct: Mapped[Decimal | None] = mapped_column(Dinero)  # 0 → se deduce de periodos_vida
    iva_soportado: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))  # regularización IVA bien inversión
    factura_compra_id: Mapped[int | None] = mapped_column(ForeignKey("factura.id"))
    asiento_baja_id: Mapped[int | None] = mapped_column(ForeignKey("asiento.id"))  # asiento que retira el bien al darlo de baja
    notas: Mapped[str | None] = mapped_column(Text)

    cuenta_inmovilizado: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_inmovilizado_id])
    cuenta_amortizacion: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_amortizacion_id])
    cuenta_dotacion: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_dotacion_id])
    amortizaciones: Mapped[list[AmortizacionPeriodo]] = relationship(
        back_populates="bien", order_by="AmortizacionPeriodo.desde", cascade="all, delete-orphan"
    )


class AmortizacionPeriodo(Base):
    """Una línea del cuadro de amortización: un periodo (normalmente un año) con lo previsto y lo realizado."""

    __tablename__ = "amortizacion_periodo"
    __table_args__ = (UniqueConstraint("bien_id", "desde"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    bien_id: Mapped[int] = mapped_column(ForeignKey("bien_inversion.id", ondelete="CASCADE"))
    anio: Mapped[int] = mapped_column(Integer)
    desde: Mapped[date] = mapped_column(Date)
    hasta: Mapped[date] = mapped_column(Date)
    importe_previsto: Mapped[Decimal] = mapped_column(Dinero)
    importe_contable: Mapped[Decimal | None] = mapped_column(Dinero)  # nulo = aún sin amortizar
    importe_fiscal: Mapped[Decimal | None] = mapped_column(Dinero)
    # MGD: 'M' importe introducido a mano · 'X' establecido por un asiento extra; el programa anterior: asiento 2025.9.5
    origen: Mapped[str | None] = mapped_column(String(1))
    asiento_id: Mapped[int | None] = mapped_column(ForeignKey("asiento.id"))

    bien: Mapped[BienInversion] = relationship(back_populates="amortizaciones")


class DeclaracionPresentada(Base):
    """Declaración ya presentada a la AEAT (hoy el modelo 303), con sus casillas, tal como está en el programa anterior. Es de sólo lectura:
    sirve para comprobar que la liquidación contabilizada coincide con lo presentado y para validar los modelos que calculemos.
    """

    __tablename__ = "declaracion_presentada"
    __table_args__ = (UniqueConstraint("empresa_id", "modelo", "anio", "periodo", "tipo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    modelo: Mapped[str] = mapped_column(String(4))
    anio: Mapped[int] = mapped_column(Integer)
    periodo: Mapped[int] = mapped_column(Integer)  # 1–4 trimestres
    tipo: Mapped[int] = mapped_column(Integer, default=1)  # TIPDEC del programa anterior (1 la que se contabilizó; otros, p. ej. una complementaria)
    fecha_emision: Mapped[date | None] = mapped_column(Date)
    fecha_envio: Mapped[date | None] = mapped_column(Date)
    justificante: Mapped[str | None] = mapped_column(String(32))
    resultado_liquidacion: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))  # casilla 46: positivo = a ingresar
    resultado: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))  # casilla 71: tras compensar periodos anteriores
    a_compensar: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))  # casilla 87
    casillas: Mapped[str | None] = mapped_column(Text)  # JSON {casilla: importe} con las casillas distintas de cero
    asiento_id: Mapped[int | None] = mapped_column(ForeignKey("asiento.id"))  # el asiento de liquidación con que se contabilizó
    # el PDF presentado (exportado del programa anterior), en el almacén de justificantes: <empresa>/<año>/D/<id>_<nombre>
    pdf_nombre: Mapped[str | None] = mapped_column(String(255))
    pdf_ruta: Mapped[str | None] = mapped_column(String(512))
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))

    lineas: Mapped[list[DeclaracionLinea]] = relationship(back_populates="declaracion", cascade="all, delete-orphan", order_by="DeclaracionLinea.id")
    asiento: Mapped[Asiento | None] = relationship()


class DeclaracionLinea(Base):
    """Factura incluida en una declaración, con la casilla en que se declaró (el programa anterior 444)."""

    __tablename__ = "declaracion_linea"

    id: Mapped[int] = mapped_column(primary_key=True)
    declaracion_id: Mapped[int] = mapped_column(ForeignKey("declaracion_presentada.id", ondelete="CASCADE"))
    factura_id: Mapped[int | None] = mapped_column(ForeignKey("factura.id"))
    numero_factura: Mapped[str | None] = mapped_column(String(40))
    fecha_factura: Mapped[date | None] = mapped_column(Date)
    fecha_fiscal: Mapped[date | None] = mapped_column(Date)
    casilla: Mapped[str | None] = mapped_column(String(4))
    base: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    porcentaje: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    cuota: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))

    declaracion: Mapped[DeclaracionPresentada] = relationship(back_populates="lineas")
    factura: Mapped[Factura | None] = relationship()


# Estados de una presentación a la AEAT (ver `servicios/presentacion303.py`)
BORRADOR, GENERADA, PRESENTADA, RECHAZADA, SUSTITUIDA, DESCARTADA = "borrador", "generada", "presentada", "rechazada", "sustituida", "descartada"


class PresentacionAeat(Base):
    """Una autoliquidación preparada, presentada o rechazada por nosotros (303 ahora; 111, 202… con el mismo molde).

    Congela lo que se calculó (casillas) y lo que se generó (fichero y su huella, versión del diseño de registro) para poder demostrar después qué se
    presentó y con qué especificación. Una presentación `presentada` bloquea su periodo: sólo se puede rectificar con otra de tipo rectificativa.
    Las declaraciones presentadas antes de usar este programa viven en `DeclaracionPresentada` (importadas del programa anterior).
    """

    __tablename__ = "presentacion_aeat"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    modelo: Mapped[str] = mapped_column(String(4))
    anio: Mapped[int] = mapped_column(Integer)
    periodo: Mapped[str] = mapped_column(String(2))  # "1T".."4T" (o "01".."12")
    estado: Mapped[str] = mapped_column(String(12), default=BORRADOR)
    tipo_presentacion: Mapped[str] = mapped_column(String(14), default="normal")  # normal · rectificativa (el 303 de 2026 no distingue complementaria de sustitutiva)
    tipo_declaracion: Mapped[str] = mapped_column(String(1), default="C")  # el del fichero: C compensación · I ingreso · U domiciliación · N sin actividad…
    resultado: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))  # casilla 71
    casillas: Mapped[str | None] = mapped_column(Text)  # JSON {casilla: importe} congelado al crear el borrador
    prorrata: Mapped[Decimal | None] = mapped_column(Dinero)  # casilla 44 tal como se introdujo a mano
    bolsa_inicial: Mapped[Decimal | None] = mapped_column(Dinero)  # cuotas a compensar con las que se calculó (casilla 110)
    bolsa_manual: Mapped[bool] = mapped_column(default=False)  # la bolsa se introdujo a mano porque el trimestre anterior no consta presentado
    rectifican: Mapped[str | None] = mapped_column(Text)  # JSON con los ids de las rectificativas que van a las casillas 40 y 41
    domiciliar: Mapped[bool] = mapped_column(default=True)
    baja_domiciliacion: Mapped[bool] = mapped_column(default=False)  # rectificativa favorable: se pide modificar o dar de baja la domiciliación de la anterior
    nrc_importe: Mapped[Decimal | None] = mapped_column(Dinero)  # resultado (casilla 71) cuando se anotó el NRC: el NRC sólo vale para ese importe exacto
    nrc: Mapped[str | None] = mapped_column(String(22))  # número de referencia completo del pago, si no se domicilia (se pide al presentar, no va en el fichero)
    anterior_id: Mapped[int | None] = mapped_column(ForeignKey("presentacion_aeat.id"))  # la presentación que ésta complementa o sustituye
    diseno_version: Mapped[str | None] = mapped_column(String(32))  # p. ej. DR303e26v101
    diseno_sha256: Mapped[str | None] = mapped_column(String(64))
    fichero_nombre: Mapped[str | None] = mapped_column(String(128))
    fichero_sha256: Mapped[str | None] = mapped_column(String(64))
    fichero_ruta: Mapped[str | None] = mapped_column(String(512))
    justificante: Mapped[str | None] = mapped_column(String(32))  # nº de justificante que devuelve la AEAT
    csv: Mapped[str | None] = mapped_column(String(32))
    respuesta_ruta: Mapped[str | None] = mapped_column(String(512))  # respuesta de la AEAT y resguardo en PDF
    respuesta_sha256: Mapped[str | None] = mapped_column(String(64))
    creada_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    creada_por: Mapped[str | None] = mapped_column(String(64))
    presentada_en: Mapped[datetime | None] = mapped_column(DateTime)
    presentada_por: Mapped[str | None] = mapped_column(String(64))
    observaciones: Mapped[str | None] = mapped_column(Text)

    eventos: Mapped[list[PresentacionEvento]] = relationship(back_populates="presentacion", cascade="all, delete-orphan", order_by="PresentacionEvento.id")


class PresentacionEvento(Base):
    """Historial de una presentación (creada, fichero generado, presentada, rechazada…): quién, cuándo y qué."""

    __tablename__ = "presentacion_evento"

    id: Mapped[int] = mapped_column(primary_key=True)
    presentacion_id: Mapped[int] = mapped_column(ForeignKey("presentacion_aeat.id", ondelete="CASCADE"))
    momento: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    usuario: Mapped[str | None] = mapped_column(String(64))
    evento: Mapped[str] = mapped_column(String(32))
    detalle: Mapped[str | None] = mapped_column(Text)

    presentacion: Mapped[PresentacionAeat] = relationship(back_populates="eventos")


# Estados de una legalización de libros (ver `servicios/libros_oficiales.py`)
PREPARADA, ENVIADA = "preparada", "enviada"


class Legalizacion(Base):
    """La legalización de los libros de un ejercicio en el Registro Mercantil: lo que se preparó para Legalia2 (el ZIP con los cuatro libros) y, cuando se envía, su acuse."""

    __tablename__ = "legalizacion"
    __table_args__ = (UniqueConstraint("empresa_id", "anio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    anio: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(12), default=PREPARADA)
    preparada_en: Mapped[datetime | None] = mapped_column(DateTime)
    preparada_por: Mapped[str | None] = mapped_column(String(64))
    fecha_presentacion: Mapped[date | None] = mapped_column(Date)  # la que va en DATOS.TXT (código 101)
    zip_nombre: Mapped[str | None] = mapped_column(String(64))
    zip_ruta: Mapped[str | None] = mapped_column(String(512))
    zip_sha256: Mapped[str | None] = mapped_column(String(64))
    enviada_en: Mapped[date | None] = mapped_column(Date)
    referencia: Mapped[str | None] = mapped_column(String(64))  # el número de documento del acuse de entrada del Registro
    numero_entrada: Mapped[str | None] = mapped_column(String(32))  # «2026 / 3 / 623888»: el nº de entrada que asigna el Registro
    acuse_ruta: Mapped[str | None] = mapped_column(String(512))

    libros: Mapped[list[LibroLegalizacion]] = relationship(back_populates="legalizacion", cascade="all, delete-orphan", order_by="LibroLegalizacion.orden")


class DepositoCuentas(Base):
    """El depósito de las cuentas anuales de un ejercicio en el Registro Mercantil: lo que se preparó para D2 (el formulario `DEPOSITO.XML` y la memoria) y, cuando se envía, su acuse."""

    __tablename__ = "deposito_cuentas"
    __table_args__ = (UniqueConstraint("empresa_id", "anio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    anio: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(String(12), default=PREPARADA)
    fecha_formulacion: Mapped[date | None] = mapped_column(Date)  # cuando los administradores formularon las cuentas
    fecha_aprobacion: Mapped[date | None] = mapped_column(Date)  # la de la junta que las aprobó (el plazo del depósito corre desde aquí)
    pmp_actual: Mapped[int | None] = mapped_column(Integer)  # periodo medio de pago a proveedores, en días (memoria: deber de información)
    pmp_anterior: Mapped[int | None] = mapped_column(Integer)
    mujeres_organo: Mapped[int | None] = mapped_column(Integer)  # mujeres entre los miembros del órgano de administración (datos de cierre de D2)
    miembros_organo: Mapped[int | None] = mapped_column(Integer)  # total de miembros del órgano de administración
    mujeres_organo_anterior: Mapped[int | None] = mapped_column(Integer)
    miembros_organo_anterior: Mapped[int | None] = mapped_column(Integer)
    cierre: Mapped[str | None] = mapped_column(Text)  # JSON con el resto de los «datos de cierre» (personal, certificación, memoria, periodo de pago, base de reparto): ver servicios/deposito_cuentas.py
    zip_nombre: Mapped[str | None] = mapped_column(String(64))
    zip_huella: Mapped[str | None] = mapped_column(String(64))  # SHA-256 (base64) del ZIP que prepara Conta: sirve para saber si cambió desde que se importó en D2
    huella_d2: Mapped[str | None] = mapped_column(String(64))  # la huella digital que genera D2 al importar el ZIP (D2 la calcula sobre su propio ZIP): es la que lleva la certificación
    preparado_en: Mapped[datetime | None] = mapped_column(DateTime)
    preparado_por: Mapped[str | None] = mapped_column(String(64))
    carpeta_ruta: Mapped[str | None] = mapped_column(String(512))  # la carpeta del depósito para D2, relativa al almacén
    xml_sha256: Mapped[str | None] = mapped_column(String(64))
    enviado_en: Mapped[date | None] = mapped_column(Date)
    referencia: Mapped[str | None] = mapped_column(String(64))
    numero_entrada: Mapped[str | None] = mapped_column(String(32))
    acuse_ruta: Mapped[str | None] = mapped_column(String(512))


class ImpuestoSociedades(Base):
    """Los datos que el modelo 200 de un ejercicio necesita y que no salen de la contabilidad: caracteres de la declaración, datos de cierre, correcciones al resultado,
    retenciones y pagos, y los apartados opcionales (reinversión, donativos, deducciones). Van en un JSON (ver `servicios/impuesto_sociedades_datos.py`) para poder ampliarlos sin migrar."""

    __tablename__ = "impuesto_sociedades"
    __table_args__ = (UniqueConstraint("empresa_id", "anio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    anio: Mapped[int] = mapped_column(Integer)
    datos: Mapped[str | None] = mapped_column(Text)
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime)


class BaseNegativa(Base):
    """Una base imponible negativa pendiente de compensar (art. 26 LIS), por año de origen. `pendiente_manual` sustituye a `base − aplicado` cuando se arrastra el saldo de otro programa."""

    __tablename__ = "base_negativa"
    __table_args__ = (UniqueConstraint("empresa_id", "anio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    anio: Mapped[int] = mapped_column(Integer)  # el ejercicio en que se generó
    base: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))  # importe de la base negativa (en positivo)
    aplicado: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))  # lo ya compensado en ejercicios posteriores
    pendiente_manual: Mapped[Decimal | None] = mapped_column(Dinero)

    @property
    def pendiente(self) -> Decimal:
        return self.pendiente_manual if self.pendiente_manual is not None else max(self.base - self.aplicado, Decimal("0.00"))


class LibroLegalizacion(Base):
    """Uno de los cuatro libros de una legalización: su número de libro en el Registro, el PDF generado y su huella."""

    __tablename__ = "legalizacion_libro"

    id: Mapped[int] = mapped_column(primary_key=True)
    legalizacion_id: Mapped[int] = mapped_column(ForeignKey("legalizacion.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)  # 1 diario, 2 inventario y cuentas anuales, 3 socios, 4 actas
    clave: Mapped[str] = mapped_column(String(12))
    numero: Mapped[int] = mapped_column(Integer)  # nº de libro (00i02 de DATOS.TXT)
    fecha_ejercicio_anterior: Mapped[date | None] = mapped_column(Date)  # 00i05: fin del ejercicio de la legalización anterior de este libro (vacío la primera vez)
    fichero_nombre: Mapped[str | None] = mapped_column(String(64))
    fichero_ruta: Mapped[str | None] = mapped_column(String(512))
    sha256_base64: Mapped[str | None] = mapped_column(String(64))
    paginas: Mapped[int | None] = mapped_column(Integer)

    legalizacion: Mapped[Legalizacion] = relationship(back_populates="libros")


class Socio(Base):
    """Un socio de la sociedad, para el libro registro de socios. Sus altas y bajas de participaciones están en `MovimientoSocio`."""

    __tablename__ = "socio"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    nif: Mapped[str | None] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(128))  # «Apellidos, Nombre» o la razón social
    nacionalidad: Mapped[str | None] = mapped_column(String(32))
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    domicilio: Mapped[str | None] = mapped_column(String(128))
    poblacion: Mapped[str | None] = mapped_column(String(64))
    provincia: Mapped[str | None] = mapped_column(String(32))
    profesion: Mapped[str | None] = mapped_column(String(64))
    estado_civil: Mapped[str | None] = mapped_column(String(32))

    movimientos: Mapped[list[MovimientoSocio]] = relationship(back_populates="socio", cascade="all, delete-orphan", order_by="MovimientoSocio.fecha, MovimientoSocio.id")


class MovimientoSocio(Base):
    """Constitución, compra, venta, ampliación… de las participaciones de un socio. `participaciones` lleva signo: una baja resta."""

    __tablename__ = "movimiento_socio"

    id: Mapped[int] = mapped_column(primary_key=True)
    socio_id: Mapped[int] = mapped_column(ForeignKey("socio.id", ondelete="CASCADE"))
    fecha: Mapped[date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(String(32), default="Constitución")
    concepto: Mapped[str | None] = mapped_column(String(128))
    participaciones: Mapped[int] = mapped_column(Integer, default=0)
    desde: Mapped[int | None] = mapped_column(Integer)  # numeración de las participaciones (opcional)
    hasta: Mapped[int | None] = mapped_column(Integer)
    valor_nominal: Mapped[str] = mapped_column(String(14), default="1.00")  # decimal en texto: hay sociedades con cuatro decimales (6,0101 €)

    socio: Mapped[Socio] = relationship(back_populates="movimientos")


class Acta(Base):
    """Un acta del libro registro de actas (la reunión de la Junta, normalmente la de aprobación de cuentas). Entra en el libro del ejercicio al que pertenece su fecha."""

    __tablename__ = "acta"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    numero: Mapped[int] = mapped_column(Integer)
    fecha: Mapped[date] = mapped_column(Date)
    hora_inicio: Mapped[str | None] = mapped_column(String(5))
    hora_fin: Mapped[str | None] = mapped_column(String(5))
    clase: Mapped[str] = mapped_column(String(32), default="Ordinaria")
    organo: Mapped[str] = mapped_column(String(48), default="Junta General")
    asistentes: Mapped[str | None] = mapped_column(Text)  # uno por línea
    orden_del_dia: Mapped[str | None] = mapped_column(Text)
    resumen: Mapped[str | None] = mapped_column(Text)
    intervenciones: Mapped[str | None] = mapped_column(Text)
    acuerdos: Mapped[str | None] = mapped_column(Text)
    votaciones: Mapped[str | None] = mapped_column(Text)
    presidente_nombre: Mapped[str | None] = mapped_column(String(128))
    presidente_nif: Mapped[str | None] = mapped_column(String(20))
    secretario_nombre: Mapped[str | None] = mapped_column(String(128))
    secretario_nif: Mapped[str | None] = mapped_column(String(20))


class Parametro(Base):
    """Parámetros de empresa (clave/valor, como `Param.dbf` de MGD): PTE_APLIC, PYG, IVA_DEBE…"""

    __tablename__ = "parametro"
    __table_args__ = (UniqueConstraint("empresa_id", "clave"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    clave: Mapped[str] = mapped_column(String(64))
    valor: Mapped[str | None] = mapped_column(Text)


# --- Tesorería -------------------------------------------------------------------------------------------
# Ver docs/pseudocodigo/02_tesoreria.md. Lo derivado (pendiente de un vencimiento, saldo de un banco) NO se guarda:
# se calcula en `domain.tesoreria` para que no pueda desincronizarse.

BANCO_NORMAL = "B"
BANCO_COMPENSACION = "C"  # MGD banco -1: compensación de vencimientos
BANCO_REMESAS = "R"  # MGD banco -3: remesas de vencimientos


class FormaPago(Base):
    """Forma de cobro/pago (MGD `Tipovtos`): giro, efecto…"""

    __tablename__ = "forma_pago"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    numero_origen: Mapped[int] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(String(32))
    por_defecto_clientes: Mapped[bool] = mapped_column(default=False)
    por_defecto_proveedores: Mapped[bool] = mapped_column(default=False)


class Banco(Base):
    __tablename__ = "banco"
    __table_args__ = (
        UniqueConstraint("empresa_id", "numero"),
        CheckConstraint("clase IN ('B','C','R')"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    numero: Mapped[int] = mapped_column(Integer)  # MGD Bancos.NUMERO (−1 compensación, −3 remesas)
    clase: Mapped[str] = mapped_column(String(1), default=BANCO_NORMAL)
    nombre: Mapped[str] = mapped_column(String(64))
    sucursal: Mapped[str | None] = mapped_column(String(64))
    iban: Mapped[str | None] = mapped_column(String(34))  # MGD NUMCTA
    bic: Mapped[str | None] = mapped_column(String(11))
    cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    saldo_inicial: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    orden: Mapped[int | None] = mapped_column(Integer)  # el lugar del banco en las listas para elegirlo (1 = el primero); los que no lo tienen van detrás, por su número

    cuenta: Mapped[Cuenta | None] = relationship()


class Vencimiento(Base):
    """Vencimiento de una factura, de un apunte de extra o de una remesa.

    `importe` con signo: positivo = a cobrar, negativo = a pagar. La cuenta efectiva se calcula así (ver
    `domain.tesoreria.cuenta_efectiva`): `cuenta_id` si está rellena; si no, la de defecto (remesas), la del tercero de la
    factura, o la del apunte del extra (`cuenta_origen_id`).
    """

    __tablename__ = "vencimiento"
    __table_args__ = (
        CheckConstraint("origen_tipo IN ('E','R','X','B')"),
        Index("ix_vencimiento_origen", "ejercicio_id", "origen_tipo", "origen_numero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ejercicio_id: Mapped[int] = mapped_column(ForeignKey("ejercicio.id"))
    numero_origen_mgd: Mapped[int | None] = mapped_column(Integer)  # Vtos.NUMERO (trazabilidad de la migración)
    origen_tipo: Mapped[str] = mapped_column(String(1))  # E emitida · R recibida · X extra · B remesa
    origen_numero: Mapped[int] = mapped_column(Integer)  # Vtos.TPNUMERO
    factura_id: Mapped[int | None] = mapped_column(ForeignKey("factura.id"))
    apunte_id: Mapped[int | None] = mapped_column(ForeignKey("apunte.id"))  # vencimientos de un asiento manual (extra)
    fecha: Mapped[date | None] = mapped_column(Date)
    importe: Mapped[Decimal] = mapped_column(Dinero)
    cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))  # devengo explícito (≠ la normal)
    cuenta_defecto_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    cuenta_origen_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))  # cuenta del apunte (extras)
    banco_previsto_id: Mapped[int | None] = mapped_column(ForeignKey("banco.id"))
    forma_pago_id: Mapped[int | None] = mapped_column(ForeignKey("forma_pago.id"))

    factura: Mapped[Factura | None] = relationship()
    apunte: Mapped[Apunte | None] = relationship()
    cuenta: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_id])
    cuenta_defecto: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_defecto_id])
    cuenta_origen: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_origen_id])
    banco_previsto: Mapped[Banco | None] = relationship()
    forma_pago: Mapped[FormaPago | None] = relationship()
    pagos: Mapped[list[Pago]] = relationship(back_populates="vencimiento")


class TipoIva(Base):
    """Tipo de IVA del catálogo de la empresa (MGD `Tipoiva`). `sentido`: R = soportado (recibidas), E = repercutido (emitidas)."""

    __tablename__ = "tipo_iva"
    __table_args__ = (UniqueConstraint("empresa_id", "sentido", "numero"), CheckConstraint("sentido IN ('E','R')"))

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    sentido: Mapped[str] = mapped_column(String(1))
    numero: Mapped[int] = mapped_column(Integer)
    texto: Mapped[str] = mapped_column(String(30))
    abreviatura: Mapped[str | None] = mapped_column(String(3))
    pct_iva: Mapped[Decimal] = mapped_column(Dinero)
    cuenta_iva_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    pct_recargo: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))
    cuenta_recargo_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))
    por_defecto: Mapped[bool] = mapped_column(default=False)
    inactivo: Mapped[bool] = mapped_column(default=False)

    cuenta_iva: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_iva_id])
    cuenta_recargo: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_recargo_id])


class Plantilla(Base):
    """Plantilla de asiento manual (MGD `Explant`): título con {año}/{mes}… y líneas Debe/Haber/Cuadre."""

    __tablename__ = "plantilla"
    __table_args__ = (UniqueConstraint("empresa_id", "titulo"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    titulo: Mapped[str] = mapped_column(String(128))

    lineas: Mapped[list[PlantillaLinea]] = relationship(
        back_populates="plantilla", cascade="all, delete-orphan", order_by="PlantillaLinea.orden"
    )


class PlantillaLinea(Base):
    """Línea de plantilla. La cuenta se guarda como **código** (puede no existir aún: se comprueba al usarla)."""

    __tablename__ = "plantilla_linea"
    __table_args__ = (CheckConstraint("dhc IN ('D','H','C')"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    plantilla_id: Mapped[int] = mapped_column(ForeignKey("plantilla.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer)
    cuenta: Mapped[str] = mapped_column(String(12))
    ayuda: Mapped[str] = mapped_column(String(64), default="")
    dhc: Mapped[str] = mapped_column(String(1))  # D debe · H haber · C cuadre (la línea que equilibra el asiento)
    importe: Mapped[Decimal] = mapped_column(Dinero, default=Decimal("0.00"))  # importe de muestra
    vencimientos: Mapped[str] = mapped_column(String(128), default="")  # reglas "D=25 M+1 A=" separadas por comas

    plantilla: Mapped[Plantilla] = relationship(back_populates="lineas")


class MovimientoBanco(Base):
    """Movimiento de un banco. Su asiento es el de tipo 3 con el mismo número."""

    __tablename__ = "movimiento_banco"
    __table_args__ = (
        UniqueConstraint("ejercicio_id", "numero"),
        Index("ix_movimiento_banco_orden", "banco_id", "fecha", "clave", "numero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ejercicio_id: Mapped[int] = mapped_column(ForeignKey("ejercicio.id"))
    banco_id: Mapped[int] = mapped_column(ForeignKey("banco.id"))
    numero: Mapped[int] = mapped_column(Integer)  # también nº del asiento tipo 3
    fecha: Mapped[date] = mapped_column(Date)
    clave: Mapped[str] = mapped_column(String(3), default="")  # orden dentro del día; "ZZZ" = automáticos
    texto: Mapped[str] = mapped_column(String(255), default="")
    texto_automatico: Mapped[bool] = mapped_column(default=False)

    banco: Mapped[Banco] = relationship()
    pagos: Mapped[list[Pago]] = relationship(
        back_populates="movimiento",
        cascade="all, delete-orphan",
        order_by="Pago.orden",
        foreign_keys="Pago.movimiento_id",
    )


class Pago(Base):
    """Línea de un movimiento: salda un vencimiento, va a una subcuenta o queda pendiente de aplicar.

    `importe` con signo desde el punto de vista del banco: positivo = entra dinero (cobro), negativo = sale (pago).
    """

    __tablename__ = "pago"
    __table_args__ = (Index("ix_pago_vencimiento", "vencimiento_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    movimiento_id: Mapped[int] = mapped_column(ForeignKey("movimiento_banco.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    importe: Mapped[Decimal] = mapped_column(Dinero)
    vencimiento_id: Mapped[int | None] = mapped_column(ForeignKey("vencimiento.id"))
    cuenta_directa_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id"))  # MGD DIRSUBCTA
    # Transferencia entre bancos (MGD BANCOT/NUMEROT): el movimiento espejo del otro banco; su `cuenta_directa`
    # es la cuenta de ese otro banco y los importes de ambos movimientos son opuestos.
    movimiento_contraparte_id: Mapped[int | None] = mapped_column(ForeignKey("movimiento_banco.id"))
    declaracion_terceros: Mapped[bool] = mapped_column(default=False)

    movimiento: Mapped[MovimientoBanco] = relationship(back_populates="pagos", foreign_keys=[movimiento_id])
    movimiento_contraparte: Mapped[MovimientoBanco | None] = relationship(foreign_keys=[movimiento_contraparte_id])
    vencimiento: Mapped[Vencimiento | None] = relationship(back_populates="pagos")
    cuenta_directa: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_directa_id])


# --- Extractos del banco ---------------------------------------------------------------------------------


class Extracto(Base):
    """Un fichero de extracto importado (una descarga del banco o de la tarjeta)."""

    __tablename__ = "extracto"

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    banco_id: Mapped[int] = mapped_column(ForeignKey("banco.id"))
    fichero: Mapped[str] = mapped_column(String(255))
    huella: Mapped[str] = mapped_column(String(64))  # SHA-256 del fichero: avisa si se importa dos veces
    formato: Mapped[str] = mapped_column(String(16))  # bbva, caixabank, santander, tarjeta
    desde: Mapped[date | None] = mapped_column(Date)
    hasta: Mapped[date | None] = mapped_column(Date)
    lineas: Mapped[int] = mapped_column(Integer, default=0)  # las que traía el fichero
    nuevas: Mapped[int] = mapped_column(Integer, default=0)  # las que no estaban ya guardadas
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    banco: Mapped[Banco] = relationship()


class ExtractoLinea(Base):
    """Una línea de un extracto, tal como la da el banco. `importe` con el signo del Mayor de esa cuenta: positivo = entra dinero (debe), negativo = sale (haber)."""

    __tablename__ = "extracto_linea"
    __table_args__ = (
        UniqueConstraint("banco_id", "clave"),
        Index("ix_extracto_linea_banco_fecha", "banco_id", "fecha"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    extracto_id: Mapped[int] = mapped_column(ForeignKey("extracto.id", ondelete="CASCADE"))
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    banco_id: Mapped[int] = mapped_column(ForeignKey("banco.id"))
    orden: Mapped[int] = mapped_column(Integer, default=0)  # posición dentro del fichero, en orden cronológico
    fecha: Mapped[date] = mapped_column(Date)
    fecha_valor: Mapped[date | None] = mapped_column(Date)
    texto: Mapped[str] = mapped_column(String(255), default="")
    mas_datos: Mapped[str] = mapped_column(String(255), default="")
    importe: Mapped[Decimal] = mapped_column(Dinero)
    saldo: Mapped[Decimal | None] = mapped_column(Dinero)  # la tarjeta no lo trae
    clave: Mapped[str] = mapped_column(String(40))  # identifica la línea para no repetirla al importar extractos que se solapan
    movimiento_id: Mapped[int | None] = mapped_column(ForeignKey("movimiento_banco.id", ondelete="SET NULL"))  # el movimiento de banco creado al conciliarla con una factura

    extracto: Mapped[Extracto] = relationship()
    banco: Mapped[Banco] = relationship()



# --- Lista de trabajo del trimestre -----------------------------------------------------------------------


class FacturaTrimestre(Base):
    """Una factura de la lista de trabajo del trimestre: viene del Excel de Verifactu y espera a conciliarse con el extracto.

    Todavía no es una factura contable: al «aplicar» se crea la `Factura` y el movimiento de banco, y se anota aquí en `factura_id`.
    """

    __tablename__ = "factura_trimestre"
    __table_args__ = (
        UniqueConstraint("empresa_id", "sentido", "clave"),
        Index("ix_factura_trimestre_empresa", "empresa_id", "sentido", "fecha_factura"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    sentido: Mapped[str] = mapped_column(String(1), default="R")  # R recibida, E emitida
    clave: Mapped[str] = mapped_column(String(80))  # nif|nº factura|fecha|total: evita cargar dos veces la misma
    fichero: Mapped[str] = mapped_column(String(255), default="")
    nombre: Mapped[str] = mapped_column(String(255), default="")
    nif: Mapped[str] = mapped_column(String(32), default="")
    fecha_factura: Mapped[date] = mapped_column(Date)
    numero_factura: Mapped[str] = mapped_column(String(60), default="")
    base: Mapped[Decimal | None] = mapped_column(Dinero)
    porcentaje_iva: Mapped[Decimal | None] = mapped_column(Dinero)
    cuota_iva: Mapped[Decimal | None] = mapped_column(Dinero)
    total: Mapped[Decimal] = mapped_column(Dinero)
    iva_extra: Mapped[str] = mapped_column(String(120), default="")  # 2.º y 3.er tipo de IVA como «% cuota;% cuota»
    ruta_pdf: Mapped[str] = mapped_column(String(500), default="")
    fecha_contable: Mapped[date | None] = mapped_column(Date)
    pago_fecha: Mapped[date | None] = mapped_column(Date)  # lo que Verifactu ya sabía del pago, sólo como referencia
    pago_concepto: Mapped[str] = mapped_column(String(255), default="")
    pago_subcuenta: Mapped[str] = mapped_column(String(20), default="")
    factura_id: Mapped[int | None] = mapped_column(ForeignKey("factura.id", ondelete="SET NULL"))
    descartada: Mapped[bool] = mapped_column(default=False)  # la quitó el usuario (repetida, no es del trimestre…): sigue guardada para que cargar el mismo Excel no la devuelva
    descartada_por: Mapped[str | None] = mapped_column(String(12))  # «borrada» (la quitó el usuario: al cargar de nuevo el Excel vuelve) o «duplicada» (copia de Verifactu: no vuelve)
    # lo que el usuario ha decidido para esta factura (si no, se busca el proveedor por la correspondencia, por NIF o por nombre)
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id", ondelete="SET NULL"))  # el proveedor de Conta
    cuenta_gasto_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id", ondelete="SET NULL"))  # la subcuenta de gasto, si no es la del proveedor
    crear_proveedor: Mapped[bool] = mapped_column(default=False)  # crear el proveedor con los datos de Verifactu
    # quién la pagó cuando no hay línea de extracto que lo diga (un socio que adelanta el dinero): el banco o cuenta de socio elegido y el día del pago
    pagada_por_id: Mapped[int | None] = mapped_column(ForeignKey("banco.id", ondelete="SET NULL"))
    pagada_fecha: Mapped[date | None] = mapped_column(Date)
    creado: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class CorrespondenciaTercero(Base):
    """«Cuando Verifactu traiga este NIF, el proveedor de Conta es éste.» Por ejemplo, el NIF real de un hotel con el proveedor genérico de tickets de aparcamiento."""

    __tablename__ = "correspondencia_tercero"
    __table_args__ = (UniqueConstraint("empresa_id", "nif"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    nif: Mapped[str] = mapped_column(String(32))  # el de Verifactu, normalizado (sin espacios ni guiones, en mayúsculas)
    tercero_id: Mapped[int] = mapped_column(ForeignKey("tercero.id", ondelete="CASCADE"))
    cuenta_gasto_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id", ondelete="SET NULL"))  # si se quiere otra de gasto que la del proveedor

    tercero: Mapped[Tercero] = relationship()


class PalabraConciliacion(Base):
    """Une un nombre de proveedor con la palabra que aparece en el banco (p. ej. «Anthropic, PBC» ↔ «Compra Anthropic»)."""

    __tablename__ = "palabra_conciliacion"
    __table_args__ = (UniqueConstraint("empresa_id", "nombre", "palabra"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    nombre: Mapped[str] = mapped_column(String(255))
    palabra: Mapped[str] = mapped_column(String(255))


class ReglaLinea(Base):
    """Qué hacer con las líneas del extracto que no tienen factura cuando su concepto es de cierto tipo (se guarda con «Recordar»).

    `patron`: el concepto sin cifras ni signos, en minúsculas («seitt», «adeslas madrid», «v negocios cred»). `tratamiento`: «cuenta» (el movimiento va contra la subcuenta `cuenta_id`: socio, liquidación de la
    tarjeta, impuestos…) o «ticket» (una factura sin IVA del proveedor `tercero_id`, con su gasto, pagada por la línea).
    """

    __tablename__ = "regla_linea"
    __table_args__ = (UniqueConstraint("empresa_id", "patron"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    patron: Mapped[str] = mapped_column(String(120))
    tratamiento: Mapped[str] = mapped_column(String(10))
    cuenta_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id", ondelete="SET NULL"))
    tercero_id: Mapped[int | None] = mapped_column(ForeignKey("tercero.id", ondelete="SET NULL"))
    gasto_id: Mapped[int | None] = mapped_column(ForeignKey("cuenta.id", ondelete="SET NULL"))  # sólo si el ticket no va a la subcuenta de gasto del proveedor

    cuenta: Mapped[Cuenta | None] = relationship(foreign_keys=[cuenta_id])
    tercero: Mapped[Tercero | None] = relationship()
