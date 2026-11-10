"""El `DEPOSITO.xbrl` del depósito de cuentas: las cuentas anuales en el formato XBRL del ICAC que exige el BOE (D2 rechaza un ZIP que no lo lleve).

Sigue el que generó el programa anterior para 2025 (taxonomía PGC-PYMES v171, espacios de nombres de 2025-01-01), el que D2 importó: identificación de la sociedad, actividad (CNAE-2025), personal, órgano de administración, periodo medio de pago,
fechas de las cuentas y, después, el balance y la cuenta de pérdidas y ganancias del ejercicio y del anterior. Los elementos de cada línea son los de la taxonomía oficial v171 del ICAC (pgc-07-c-bs y pgc-07-c-ap: «otros deudores», «otras deudas», «otros acreedores» y «otras reservas» van con el prefijo c-ap, y si van con c-bs D2 no los reconoce). Una línea con importe
y sin elemento no se escribe y el control del depósito lo avisa como error, para no depositar un XBRL que no sume.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from xml.sax.saxutils import escape

VERSION_TAXONOMIA = 2025  # el año de los espacios de nombres y de pgc07-pymes.xsd (v171): si D2 trae otra versión hay que revisarla
ESQUEMA = "https://www.icac.gob.es/sites/default/files/pgc2007/v171/pgc07-pymes.xsd"
ESPACIOS = (
    ("pgc07p", "http://www.icac.meh.es/es/fr/gaap/pgc07/cuentas/pymes/2025-01-01"),
    ("xbrldi", "http://xbrl.org/2006/xbrldi"),
    ("pgc-07-p-bal", "http://www.icac.meh.es/es/fr/gaap/pgc07/cuentas/pymes/balance/2025-01-01"),
    ("pgc-07-c-ap", "http://www.icac.meh.es/es/fr/gaap/pgc07/comun-abreviadopymes/2025-01-01"),
    ("dgi-gen-bas", "http://www.xbrl.org.es/es/2008/dgi/gp/gen-bas/2025-01-01"),
    ("xsi", "http://www.w3.org/2001/XMLSchema-instance"),
    ("pgc07mp", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/pymes/2025-01-01"),
    ("iso4217", "http://www.xbrl.org/2003/iso4217"),
    ("pgc07m-roles", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/roles/2025-01-01"),
    ("pgc-07-c-bs", "http://www.icac.meh.es/es/fr/gaap/pgc07/comun-base/2025-01-01"),
    ("dgi-cnae-25", "http://www.xbrl.org.es/es/2008/dgi/gp/lc-cnae-2025/2025-01-01"),
    ("dgi-gen-ex", "http://www.xbrl.org.es/es/2008/dgi/gp/gen-ex/2025-01-01"),
    ("xlink", "http://www.w3.org/1999/xlink"),
    ("pgc-07-ref", "http://www.icac.meh.es/es/fr/gaap/pgc07/referenceParts/2025-01-01"),
    ("dgi-rel", "http://www.xbrl.org.es/es/2008/dgi/gp/rel/2025-01-01"),
    ("dgi-lc-int", "http://www.xbrl.org.es/es/2008/dgi/gp/lc-int/2025-01-01"),
    ("pgc07mc-apdo0", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/comun/apartado0/IdentificacionGeneral/2025-01-01"),
    ("link", "http://www.xbrl.org/2003/linkbase"),
    ("dgi-eco-bas", "http://www.xbrl.org.es/es/2008/dgi/gp/eco-bas/2025-01-01"),
    ("dgi-dat-inf", "http://www.xbrl.org.es/es/2008/dgi/gp/dat-inf/2025-01-01"),
    ("xbrli", "http://www.xbrl.org/2003/instance"),
    ("pgc07d-reclsf", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/comun/ReclasificacionInstrumentosFinancieros/Dimension/2025-01-01"),
    ("pgc07m-d-pv", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/comun/PartesVinculadas/Dimension/2025-01-01"),
    ("pgc-07-p-pyg", "http://www.icac.meh.es/es/fr/gaap/pgc07/cuentas/pymes/PerdidasGanancias/2025-01-01"),
    ("dgi-est-gen", "http://www.xbrl.org.es/es/2008/dgi/gp/est-gen/2025-01-01"),
    ("pgc07mc-bs", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/comun/base/2025-01-01"),
    ("pgc07d-plzven", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/comun/PlazoVencimientoInstrumentosFinancieros/Dimension/2025-01-01"),
    ("xbrldt", "http://xbrl.org/2005/xbrldt"),
    ("pgc-07-p", "http://www.icac.meh.es/es/fr/gaap/pgc07/pymes/2025-01-01"),
    ("dgi-lc-es", "http://www.xbrl.org.es/es/2008/dgi/gp/lc-es/2025-01-01"),
    ("pgc-07-types", "http://www.icac.meh.es/es/fr/gaap/pgc07/types/2025-01-01"),
    ("pgc07mp-apdo0", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/pymes/apartado0/IdentificacionGeneral/2025-01-01"),
    ("dgi-types", "http://www.xbrl.org.es/es/2008/dgi/gp/types/2025-01-01"),
    ("pgc07mc-ap", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/comun/abreviadoPymes/2025-01-01"),
    ("pgc07d-clase", "http://www.icac.meh.es/es/fr/gaap/pgc07/memoria/comun/ClasesInstrumentosFinancieros/Dimension/2025-01-01"),
    ("pgc-07-roles", "http://www.icac.meh.es/es/fr/gaap/pgc07/roles/2025-01-01"),
    ("ref", "http://www.xbrl.org/2004/ref"),
)
BS, AP = "pgc-07-c-bs", "pgc-07-c-ap"  # la mayoría de los elementos están en el espacio «comun-base»; los de «otros deudores / otras deudas / otros acreedores / otras reservas» y «otros ingresos financieros», en «comun-abreviadopymes»
_A, _P, _G = "ActivoCorrienteDeudoresComercialesOtrasCuentasCobrar", "PasivoCorrienteAcreedoresComercialesOtrasCuentasPagar", "PerdidasGananciasOperacionesContinuadas"
# línea del balance → (espacio, elemento). Los nombres son los de la taxonomía PGC-PYMES v171 del ICAC (pgc-07-c-bs-2025-01-01.xsd y pgc-07-c-ap-2025-01-01.xsd)
ELEMENTOS_BALANCE = {
    "A": (BS, "ActivoNoCorriente"), "A.I": (BS, "ActivoNoCorrienteInmovilizadoIntangible"), "A.II": (BS, "ActivoNoCorrienteInmovilizadoMaterial"), "A.III": (BS, "ActivoNoCorrienteInversionesInmobiliarias"),
    "A.IV": (BS, "ActivoNoCorrienteInversionesEmpresasGrupoEmpresasAsociadasLargoPlazo"), "A.V": (BS, "ActivoNoCorrienteInversionesFinancierasLargoPlazo"), "A.VI": (BS, "ActivoNoCorrienteActivosImpuestoDiferido"),
    "A.VII": (BS, "ActivoNoCorrienteDeudasComercialesNoCorriente"), "B": (BS, "ActivoCorriente"), "B.I": (BS, "ActivoCorrienteExistencias"), "B.II": (BS, _A),
    "B.II.1": (BS, _A + "ClientesVentasPrestacionesServicios"), "B.II.1a": (BS, _A + "ClientesVentasPrestacionesServiciosLargoPlazo"), "B.II.1b": (BS, _A + "ClientesVentasPrestacionesServiciosCortoPlazo"),
    "B.II.2": (BS, _A + "AccionistasDesembolsosExigidos"), "B.II.3": (AP, _A + "OtrosDeudores"), "B.III": (BS, "ActivoCorrienteInversionesEmpresasGrupoEmpresasAsociadasCortoPlazo"),
    "B.IV": (BS, "ActivoCorrienteInversionesFinancierasCortoPlazo"), "B.V": (BS, "ActivoCorrientePeriodificacionesCortoPlazo"), "B.VI": (BS, "ActivoCorrienteEfectivoOtrosActivosLiquidosEquivalentes"),
    "TA": (BS, "TotalActivo"), "PN": (BS, "PatrimonioNeto"), "PN.1": (BS, "PatrimonioNetoFondosPropios"), "PN.1.I": (BS, "PatrimonioNetoFondosPropiosCapital"),
    "PN.1.I.1": (BS, "PatrimonioNetoFondosPropiosCapitalEscriturado"), "PN.1.I.2": (BS, "PatrimonioNetoFondosPropiosCapitalNoExigido"), "PN.1.II": (BS, "PatrimonioNetoFondosPropiosPrimaEmision"),
    "PN.1.III": (BS, "PatrimonioNetoFondosPropiosReservas"), "PN.1.III.1": (BS, "PatrimonioNetoFondosPropiosReservasReservaCapitalizacion"), "PN.1.III.2": (AP, "PatrimonioNetoFondosPropiosReservasOtrasReservas"),
    "PN.1.IV": (BS, "PatrimonioNetoFondosPropiosAccionesParticipacionesPatrimonioPropias"), "PN.1.V": (BS, "PatrimonioNetoFondosPropiosResultadosEjerciciosAnteriores"),
    "PN.1.VI": (BS, "PatrimonioNetoFondosPropiosOtrasAportacionesSocios"), "PN.1.VII": (BS, "PatrimonioNetoFondosPropiosResultadoEjercicio"), "PN.1.VIII": (BS, "PatrimonioNetoFondosPropiosDividendoCuenta"),
    "PN.2": (BS, "PatrimonioNetoAjustesCambioValor"), "PN.3": (BS, "PatrimonioNetoSubvencionesDonacionesLegadosRecibidos"), "PNC": (BS, "PasivoNoCorriente"),
    "PNC.I": (BS, "PasivoNoCorrienteProvisionesLargoPlazo"), "PNC.II": (BS, "PasivoNoCorrienteDeudasLargoPlazo"), "PNC.II.1": (BS, "PasivoNoCorrienteDeudasLargoPlazoDeudasEntidadesCredito"),
    "PNC.II.2": (BS, "PasivoNoCorrienteDeudasLargoPlazoAcreedoresArrendamientoFinanciero"), "PNC.II.3": (AP, "PasivoNoCorrienteDeudasLargoPlazoOtrasDeudas"),
    "PNC.III": (BS, "PasivoNoCorrienteDeudasEmpresasGrupoEmpresasAsociadasLargoPlazo"), "PNC.IV": (BS, "PasivoNoCorrientePasivosImpuestoDiferido"), "PNC.V": (BS, "PasivoNoCorrientePeriodificacionesLargoPlazo"),
    "PNC.VI": (BS, "PasivoNoCorrienteAcreedoresComercialesNoCorrientes"), "PNC.VII": (BS, "PasivoNoCorrienteDeudaCaracteristicasEspecialesLargoPlazo"), "PC": (BS, "PasivoCorriente"),
    "PC.I": (BS, "PasivoCorrienteProvisionesCortoPlazo"), "PC.II": (BS, "PasivoCorrienteDeudasCortoPlazo"), "PC.II.1": (BS, "PasivoCorrienteDeudasCortoPlazoDeudasEntidadesCredito"),
    "PC.II.2": (BS, "PasivoCorrienteDeudasCortoPlazoAcreedoresArrendamientoFinanciero"), "PC.II.3": (AP, "PasivoCorrienteDeudasCortoPlazoOtrasDeudas"),
    "PC.III": (BS, "PasivoCorrienteDeudasEmpresasGrupoEmpresasAsociadas"), "PC.IV": (BS, _P), "PC.IV.1": (BS, _P + "Proveedores"), "PC.IV.1a": (BS, _P + "ProveedoresLargoPlazo"),
    "PC.IV.1b": (BS, _P + "ProveedoresCortoPlazo"), "PC.IV.2": (AP, _P + "OtrosAcreedores"), "PC.V": (BS, "PasivoCorrientePeriodificacionesCortoPlazo"),
    "PC.VI": (BS, "PasivoCorrienteDeudasCaracteristicasEspecialesCortoPlazo"), "TP": (BS, "PatrimonioNetoPasivoTotal"),
}
ELEMENTOS_PYG = {
    "1": (BS, _G + "ImporteNetoCifraNegocios"), "2": (BS, _G + "VariacionExistenciasProductosTerminadosProductosCursoFabricacion"), "3": (BS, _G + "TrabajosRealizadosEmpresaActivo"),
    "4": (BS, _G + "Aprovisionamientos"), "5": (BS, _G + "OtrosIngresosExplotacion"), "6": (BS, _G + "GestionPersonal"), "7": (BS, _G + "OtrosGastosExplotacion"), "8": (BS, _G + "AmortizacionInmovilizado"),
    "9": (BS, _G + "ImputacionSubvencionesInmovilizadoNoFinancieroOtras"), "10": (BS, _G + "ExcesosProvisiones"), "11": (BS, _G + "DeterioroResultadoEnajenacionesInmovilizado"), "12": (BS, "PerdidasGananciasOtrosResultados"),
    "A": (BS, "PerdidasGananciasResultadoExplotacion"), "13": (BS, _G + "IngresosFinancieros"), "13a": (BS, _G + "IngresosFinancierosImputacionSubvencionesDonacionesLegadosCaracterFinanciero"),
    "13b": (AP, _G + "IngresosFinancierosOtrosIngresosFinancieros"), "14": (BS, _G + "GastosFinancieros"), "15": (BS, _G + "VariacionValorRazonableInstrumentosFinancieros"), "16": (BS, _G + "DiferenciasCambio"),
    "17": (BS, _G + "DeterioroResultadoEnajenacionesInstrumentosFinancieros"), "18": (BS, _G + "OtrosIngresosGastosCaracterFinanciero"),
    "18a": (BS, _G + "OtrosIngresosGastosCaracterFinancieroIncorporacionActivoGastosFinancieros"), "18b": (BS, _G + "OtrosIngresosGastosCaracterFinancieroIngresosFinancierosDerivadosConveniosAcreedores"),
    "18c": (BS, _G + "OtrosIngresosGastosCaracterFinancieroRestoIngresosGastos"), "B": (BS, "PerdidasGananciasResultadoFinanciero"), "C": (BS, "PerdidasGananciasResultadoAntesImpuestos"),
    "19": (BS, _G + "ImpuestosSobreBeneficios"), "D": (BS, "PerdidasGananciasResultadoEjercicio"),
}


def _n(valor: Decimal) -> str:
    return format(valor.quantize(Decimal("0.01")), "f")


def _contexto(id_: str, nif: str, inicio: date | None, fin: date) -> list[str]:
    periodo = [f"    <xbrli:instant>{fin:%Y-%m-%d}</xbrli:instant>"] if inicio is None else [f"    <xbrli:startDate>{inicio:%Y-%m-%d}</xbrli:startDate>", f"    <xbrli:endDate>{fin:%Y-%m-%d}</xbrli:endDate>"]
    return [f'<xbrli:context id="{id_}">', "  <xbrli:entity>", f'    <xbrli:identifier scheme="http://www.icac.meh.es/xbrl">{nif}</xbrli:identifier>', "  </xbrli:entity>", "  <xbrli:period>", *periodo, "  </xbrli:period>", "</xbrli:context>"]


def _cifra(contexto: str, valor) -> str:
    return f'decimals="0" contextRef="{contexto}" unitRef="pure">{Decimal(valor or 0):.2f}'


def _personal(contexto: str, p: dict | None = None) -> list[str]:
    """El personal asalariado; `p` lleva medio_fijo, medio_no_fijo, medio_discapacidad y final_{fijo,nofijo}_{h,m} (todo cero si no se indica)."""
    p = p or {}
    sexos = []
    for contrato, clave in (("TemporaryContract", "nofijo"), ("PermanentContract", "fijo")):
        sexos += [f"      <dgi-eco-bas:{contrato}>", "        <dgi-eco-bas:Gender>", f"          <dgi-eco-bas:Male {_cifra(contexto, p.get('final_' + clave + '_h'))}</dgi-eco-bas:Male>",
                  f"          <dgi-eco-bas:Female {_cifra(contexto, p.get('final_' + clave + '_m'))}</dgi-eco-bas:Female>", "        </dgi-eco-bas:Gender>", f"      </dgi-eco-bas:{contrato}>"]
    cero = _cifra(contexto, p.get("medio_discapacidad"))
    return ["<pgc07mc-apdo0:PersonalAsalariadoTupla>", "  <pgc07mc-apdo0:NumeroMediopersonasEmpleadasCursoEjercicioTipoContratoEmpleoDiscapacidad>", "    <dgi-eco-bas:EmployeesPeriodAverageNumber>",
            "      <dgi-eco-bas:TemporaryContract>", f"        <dgi-eco-bas:TemporaryContractTotal {_cifra(contexto, p.get('medio_no_fijo'))}</dgi-eco-bas:TemporaryContractTotal>", "      </dgi-eco-bas:TemporaryContract>",
            "      <dgi-eco-bas:PermanentContract>", f"        <dgi-eco-bas:PermanentContractTotal {_cifra(contexto, p.get('medio_fijo'))}</dgi-eco-bas:PermanentContractTotal>", "      </dgi-eco-bas:PermanentContract>",
            "    </dgi-eco-bas:EmployeesPeriodAverageNumber>", "  </pgc07mc-apdo0:NumeroMediopersonasEmpleadasCursoEjercicioTipoContratoEmpleoDiscapacidad>",
            f"  <dgi-eco-bas:EmployeesDisabilityLevelHigher33Total {cero}</dgi-eco-bas:EmployeesDisabilityLevelHigher33Total>", "  <pgc07mc-apdo0:PersonalAsalariadoTerminoEjercicioTipoContratoSexo>",
            "    <dgi-eco-bas:EmployeesNumberEndAccountingPeriod>", *sexos, "    </dgi-eco-bas:EmployeesNumberEndAccountingPeriod>", "  </pgc07mc-apdo0:PersonalAsalariadoTerminoEjercicioTipoContratoSexo>",
            "</pgc07mc-apdo0:PersonalAsalariadoTupla>"]


def _organo_y_pago(contexto: str, mujeres: int | None, miembros: int | None, pmp: int | None) -> list[str]:
    lineas = []
    if mujeres is not None:
        lineas.append(f'<dgi-eco-bas:NumeroMujeresOrganoAdministracion decimals="0" contextRef="{contexto}" unitRef="pure">{mujeres:.2f}</dgi-eco-bas:NumeroMujeresOrganoAdministracion>')
    if miembros is not None:
        lineas.append(f'<dgi-eco-bas:NumeroTotalMiembrosOrganoAdministracion decimals="0" contextRef="{contexto}" unitRef="pure">{miembros:.2f}</dgi-eco-bas:NumeroTotalMiembrosOrganoAdministracion>')
    if pmp is not None:
        lineas.append(f'<pgc07mc-bs:PeriodoMedioPagoPeriodoMedioPagoProveedores decimals="0" contextRef="{contexto}" unitRef="euro">{pmp:.2f}</pgc07mc-bs:PeriodoMedioPagoPeriodoMedioPagoProveedores>')
    return lineas


def _presentacion(contexto: str, inicio: date, fin: date, paginas: int = 0) -> list[str]:
    return ["<pgc07mc-apdo0:PresentacionCuentasTupla>", f'  <pgc07mc-apdo0:YearFechaInicioCuentas contextRef="{contexto}">{inicio.year}</pgc07mc-apdo0:YearFechaInicioCuentas>',
            f'  <pgc07mc-apdo0:MonthFechaInicioCuentas contextRef="{contexto}">{inicio.month:02d}</pgc07mc-apdo0:MonthFechaInicioCuentas>',
            f'  <pgc07mc-apdo0:DayFechaInicioCuentas contextRef="{contexto}">{inicio.day:02d}</pgc07mc-apdo0:DayFechaInicioCuentas>',
            f'  <pgc07mc-apdo0:YearFechaCierreCuentas contextRef="{contexto}">{fin.year}</pgc07mc-apdo0:YearFechaCierreCuentas>',
            f'  <pgc07mc-apdo0:MonthFechaCierreCuentas contextRef="{contexto}">{fin.month:02d}</pgc07mc-apdo0:MonthFechaCierreCuentas>',
            f'  <pgc07mc-apdo0:DayFechaCierreCuentas contextRef="{contexto}">{fin.day:02d}</pgc07mc-apdo0:DayFechaCierreCuentas>',
            f'  <dgi-dat-inf:TotalPagesPresented decimals="0" contextRef="{contexto}" unitRef="pure">{paginas}</dgi-dat-inf:TotalPagesPresented>', "</pgc07mc-apdo0:PresentacionCuentasTupla>"]


def lineas_sin_elemento(filas) -> list[str]:
    """Las líneas con importe que el XBRL no sabe escribir (su elemento no se ha visto en ningún XBRL real): `filas` son (id de la línea, etiqueta, actual, anterior, es_pyg)."""
    return [etiqueta for id_, etiqueta, actual, anterior, es_pyg in filas if (actual or anterior) and id_ not in (ELEMENTOS_PYG if es_pyg else ELEMENTOS_BALANCE)]


def xbrl(*, nif: str, nombre: str, domicilio: str, poblacion: str, provincia_ine: str, codigo_postal: str, telefono: str, email: str, actividad: str, cnae: str, inicio: date, fin: date,
         balance: list[tuple[str, Decimal, Decimal]], pyg: list[tuple[str, Decimal, Decimal]], mujeres: int | None, miembros: int | None, mujeres_anterior: int | None, miembros_anterior: int | None,
         pmp: int | None, pmp_anterior: int | None, personal: dict | None = None, microempresa: bool = False, paginas: int = 0, aplicacion: list[tuple[str, str, Decimal]] | None = None) -> str:
    """El `DEPOSITO.xbrl`. `balance` y `pyg` son (id de la línea, importe del ejercicio, importe del anterior) de las líneas con importe; `cnae` son las cuatro cifras de la CNAE-2025 (0125)."""
    inicio_ant, fin_ant = date(inicio.year - 1, inicio.month, inicio.day), date(fin.year - 1, fin.month, min(fin.day, 28 if fin.month == 2 else fin.day))
    nif = escape(nif)
    cnae = cnae or "0000"
    raiz = "<xbrli:xbrl " + " ".join(f'xmlns:{p}="{u}"' for p, u in ESPACIOS) + ">"
    lineas = ['<?xml version="1.0" encoding="UTF-8"?>', raiz, f'<link:schemaRef xlink:type="simple" xlink:href="{ESQUEMA}" />',
              *_contexto("I.ACTUAL", nif, None, fin), *_contexto("I.ANTERIOR", nif, None, fin_ant), *_contexto("D.ACTUAL", nif, inicio, fin), *_contexto("D.ANTERIOR", nif, inicio_ant, fin_ant),
              '<xbrli:unit id="euro">', "  <xbrli:measure>iso4217:EUR</xbrli:measure>", "</xbrli:unit>", '<xbrli:unit id="shares">', "  <xbrli:measure>xbrli:shares</xbrli:measure>", "</xbrli:unit>",
              '<xbrli:unit id="pure">', "  <xbrli:measure>xbrli:pure</xbrli:measure>", "</xbrli:unit>",
              "<pgc07mc-apdo0:IdentificacionEmpresaTupla>", '  <dgi-lc-es:Xcode_IDC.NIF contextRef="D.ACTUAL">NIF</dgi-lc-es:Xcode_IDC.NIF>',
              f'  <dgi-est-gen:IdentifierValue contextRef="D.ACTUAL">{nif}</dgi-est-gen:IdentifierValue>', '  <dgi-lc-es:Xcode_LFC.023 contextRef="D.ACTUAL">023</dgi-lc-es:Xcode_LFC.023>',
              '  <dgi-lc-es:Xcode_NMT.DS contextRef="D.ACTUAL">DS</dgi-lc-es:Xcode_NMT.DS>', f'  <dgi-est-gen:LegalNameValue contextRef="D.ACTUAL">{escape(nombre)}</dgi-est-gen:LegalNameValue>',
              '  <dgi-lc-es:Xcode_ADL.01 contextRef="D.ACTUAL">01</dgi-lc-es:Xcode_ADL.01>', f'<dgi-est-gen:AddressLine contextRef="D.ACTUAL">{escape(domicilio)}</dgi-est-gen:AddressLine>',
              f'<dgi-est-gen:MunicipalityName contextRef="D.ACTUAL">{escape(poblacion)}</dgi-est-gen:MunicipalityName>', f'<dgi-lc-es:Xcode_RCI.18 contextRef="D.ACTUAL">{provincia_ine}</dgi-lc-es:Xcode_RCI.18>',
              f'<dgi-est-gen:ZipPostalCode contextRef="D.ACTUAL">{codigo_postal}</dgi-est-gen:ZipPostalCode>', '<dgi-lc-int:Xcode_UN3155.TE contextRef="D.ACTUAL">TE</dgi-lc-int:Xcode_UN3155.TE>',
              f'<dgi-est-gen:CommunicationValue contextRef="D.ACTUAL">{telefono}</dgi-est-gen:CommunicationValue>', '<dgi-lc-int:Xcode_UN3155.EM contextRef="D.ACTUAL">EM</dgi-lc-int:Xcode_UN3155.EM>',
              f'<pgc07mc-apdo0:CommunicationValueEMail contextRef="D.ACTUAL">{escape(email)}</pgc07mc-apdo0:CommunicationValueEMail>', "</pgc07mc-apdo0:IdentificacionEmpresaTupla>",
              "<pgc07mc-apdo0:ActividadTupla>", f'  <dgi-eco-bas:ActivityDescription contextRef="D.ACTUAL">{escape(actividad.upper())}</dgi-eco-bas:ActivityDescription>',
              "  <dgi-eco-bas:ActivityCodeCNAE2025>", f'    <dgi-cnae-25:Xcode_ACC.CNAE25.{cnae} contextRef="D.ACTUAL">{cnae}</dgi-cnae-25:Xcode_ACC.CNAE25.{cnae}>',
              "  </dgi-eco-bas:ActivityCodeCNAE2025>", "</pgc07mc-apdo0:ActividadTupla>",
              *_personal("D.ACTUAL", personal), *_organo_y_pago("D.ACTUAL", mujeres, miembros, pmp), *_personal("D.ANTERIOR"), *_organo_y_pago("D.ANTERIOR", mujeres_anterior, miembros_anterior, pmp_anterior),
              *_presentacion("D.ACTUAL", inicio, fin, paginas), *_presentacion("D.ANTERIOR", inicio_ant, fin_ant),
              '<pgc07mp-apdo0:CasoAdopcionConjuntaCrteriosEspecificosMicroPyme contextRef="D.ACTUAL">' + ("true" if microempresa else "false") + "</pgc07mp-apdo0:CasoAdopcionConjuntaCrteriosEspecificosMicroPyme>"]
    for nombre_elemento, contexto, valor in aplicacion or []:  # la base de reparto y la aplicación del resultado (de la memoria): D2 las lee de aquí
        lineas.append(f'<pgc07mc-bs:AplicacionResultados{nombre_elemento} decimals="2" contextRef="{contexto}" unitRef="euro">{valor:.2f}</pgc07mc-bs:AplicacionResultados{nombre_elemento}>')
    for id_, actual, anterior in balance:
        for contexto, valor in (("I.ACTUAL", actual), ("I.ANTERIOR", anterior)):
            if id_ in ELEMENTOS_BALANCE and (valor or id_ in ("TA", "TP")):
                espacio, nombre = ELEMENTOS_BALANCE[id_]
                lineas.append(f'<{espacio}:{nombre} decimals="0" contextRef="{contexto}" unitRef="euro">{_n(valor)}</{espacio}:{nombre}>')
    for id_, actual, anterior in pyg:
        for contexto, valor in (("D.ACTUAL", actual), ("D.ANTERIOR", anterior)):
            if id_ in ELEMENTOS_PYG and valor:
                espacio, nombre = ELEMENTOS_PYG[id_]
                lineas.append(f'<{espacio}:{nombre} decimals="0" contextRef="{contexto}" unitRef="euro">{_n(valor)}</{espacio}:{nombre}>')
    lineas += ['<link:footnoteLink xlink:type="extended" xlink:role="http://www.xbrl.org/2003/role/link">', "</link:footnoteLink>", "</xbrli:xbrl>"]
    return "\n".join(lineas)
