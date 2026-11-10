# Mapa del código (Visual Objects)

| Módulo | Líneas | Clases | Rutinas |
|---|---:|---:|---:|
| _Trasvase Contaplus | 1724 | 5 | 42 |
| A_Util | 30078 | 165 | 1308 |
| B_Zip | 6907 | 10 | 274 |
| C_Datos | 9430 | 50 | 1087 |
| D_Comun | 37323 | 96 | 1139 |
| E_Edicion | 54123 | 117 | 1617 |
| E_EdicionF | 45948 | 70 | 1129 |
| F_Contabilidad | 23661 | 52 | 539 |
| G_Seguridad | 1783 | 3 | 43 |
| L_General | 5107 | 6 | 193 |
| mgd0 | 11 | 1 | 2 |
| mgdDLL | 1199 | 1 | 49 |

## _Trasvase Contaplus  (1724 líneas)


### class ExportarContabilidad  (10 métodos, 475 líneas)

CreaFicheros@656, ProcesaAsientoFactura@798, ProcesaAsiento@898, Exportar@971, DiarioTexto@1040, GrabaSubcta@1049, CierraFicheros@1091, init@1150, GrabaCuenta@1189, GrabaImporte@1193

### class vContaplus : DATAWINDOW  (6 métodos, 156 líneas)

Init@97, Directorios@163, PostInit@171, Close@179, Terminar@186, MiraDigitos@215

### class TC_Importar : DATAWINDOW  (6 métodos, 139 líneas)

Init@517, DirImportar@591, Clientes@614, Proveedores@619, AsientosImportar@625, Cuentas@631

### class vConversionCtas : DATADIALOG  (4 métodos, 130 líneas)

Init@279, Setup@320, Aceptar@348, Cancelar@384

### class TC_Exportar : DATAWINDOW  (3 métodos, 108 líneas)

Init@409, DirExportar@451, AsientosExportar@475

### class App  (1 métodos, 62 líneas)

Start@1

### funciones/procedimientos sueltos (12)

AbreEmpresa@63(34), ConvierteCta@189(26), LeeCliente@1097(18), LeeProveedor@1115(18), LeeCuenta@1133(17), LeeIvaFactura@1169(20), FicheroSubCta@1204(54), ImportarAsientosCONTAPLUS@1258(225), ImportarCliProvCONTAPLUS@1483(141), ImportarCuentasCONTAPLUS@1624(47), PonDocumento@1671(39), PonAsiento@1710(15)

## A_Util  (30078 líneas)


### class jGridE : CustomControl  (100 métodos, 2607 líneas)

Init@11413, AssignFont@11479, Destroy@11498, PaintHdr@11520, PaintRow@11597, BufferReset@11799, Dispatch@11810, VScroll@12001, MouseButtonDown@12146, Expose@12225, Anchura@12299, RowCount@12307, GetCurRec@12311, FocusChange@12315, SetupSize@12335, AlturaReg@12345, UpdateRow@12348, GetRowRect@12362, MovePtr@12373, MouseButtonDoubleClick@12388, ReadPage@12443, AjustaScroll@12539, AlturaCab@12592, DrawHLine@12597, StopCapt@12619, ColResArea@12632, MouseMove@12662, ResColWdt@12694, MouseButtonUp@12704, MouseDrag@12753, AnchoDesde@12799, AnchoHasta@12809, HScroll@12820, Tam10x@12857, aColumnas@12869, MueveColumna@12883, MueveAColumna@12898, aColumnasN@12923, BorraColumna@12933, ResetColumnas@12954, NuevaColumna@12972, PonerColumnas@12996, StartEdit@13032, GetCellRect@13192, EscondeColHasta@13203, StopEdit@13331, SetColVal@13386, siColEditable@13553, TamCabecera@13582, TamFila@13585, RefrescaCRow@13589, aTeclasControl@13604, ColorTexto@13608, ColorFondo@13611, ColorTextoCA@13615, ColorFondoCA@13618, Setup@13622, siEditableAutomatico@13647, SiScroll@13660, SiEditable@13663, SiMovColumnas@13666, SiTamColumnas@13669, UpdateRec@13673, siPreguntaColor@13706, AddColumn@13723, ColumnaActiva@13741, siLineaCompleta@13745, TamTxt@13748, AssignFixedFont@13766, siImpLineasSep@13793, siMarcoCol@13796, Refresh@13819, miraSiguienteCampo@13886, miraColCampo@13896, veteSiguiente@13905, DirEdicion@13915, DirEdicion@13918, DirEdicionSaltaA@13921, veteAlCampo@13926, SiEditable@13937, veteAbajoCampo@13940, Actualiza@13948, BufferLeeDBF@13966, BufferValor@14089, GetCurrentCellRect@14096, ColorLineas@14100, tmpColorTexto@14104, tmpColorFondo@14107, tmpColorTextoCA@14110, tmpColorFondoCA@14113, BtMirarConf@14140, BtBarCrea@14156, BtBarSitua@14170, siEstaCampo@14187, aDLVRacionaliza@14191, ReleeCabeceras@14217, DirEdicionSaltaPos@14237, PonDB@14243, ValorCampo@14248, veteAbajo@14308

### class MathiasSLE : SingleLineEdit  (37 métodos, 1450 líneas)

Dispatch@7431, KeyEvent@7541, PrevEditPos@7670, FieldSpec@7683, iTemplLen@7757, DeleteSelection@7760, IsEditPos@7877, DeleteChar@7880, InvalidAction@7969, IsValidChar@7972, PutChar@7975, UpdateEditOwner@7988, MatchesTemplChar@7999, DecimalPos@8034, ProcessChar@8044, InsertChar@8180, Init@8252, Picture@8284, Picture@8342, __Update@8345, Type@8383, TYPE@8386, UsualValue@8389, TextValue@8406, EmptyValue@8442, Paste@8468, Cut@8530, NextEditPos@8571, FocusChange@8780, __Value@8802, ConBrowser@8834, TextValue@8837, MiraPosicion@8847, PonNegativo@8857, FacilFecha@8871, PonLanzaMenu@8914, FirstNumberPosition@8951

### class vVisor : Control  (40 métodos, 1271 líneas)

Init@22684, SetNewSize@22726, SetPageSize@22750, Destroy@22765, Expose@22776, Zoom@22794, PaintPage@22846, ResetZoomPar@23007, PaintContent@23101, CloseFonts@23113, IsRectVis@23124, VBarEvent@23156, HBarEvent@23212, VScrollWnd@23254, HScrollWnd@23277, MouseButtonDown@23300, CloseImages@23310, PageReset@23324, Dispatch@23361, Muestra@23437, MuestraTexto@23466, MuestraSetup@23494, MuestraY@23544, MuestraX@23552, DivPalabras@23560, Tam@23587, MuestraForma@23595, FuentePon@23632, MuestraCuadro@23667, MuestraGrafico@23744, PaintBMP@23752, MuestraTextoBloque@23862, Line@23927, MarcaOrden@23965, MouseDrag@23970, x2Pix@23991, y2pix@23994, Alto@23998, TeclaPulsada@24004, FuenteQuita@24108

### class vCalcuDW : DIALOGWINDOW  (32 métodos, 1195 líneas)

Init@17955, BorrarHistorico@18156, ButtonClick@18166, Calcula@18176, Close@18338, ConvMoneda@18347, Dispatch@18372, EsCero@18387, Funcion@18393, FuncionDisEn@18447, FuncionEdita@18456, FuncionEvalua@18579, GrabaClipboard@18618, GrabaDB@18640, GridDobleClick@18677, GridPreguntaColor@18692, GridTeclaControl@18702, GridTeclaPulsada@18712, Inicializar@18725, LeeDB@18741, Memoria@18798, MiraDecimales@18828, Operacion@18850, PonBien@18881, PonDecimales@18887, PonMemoria@18904, Pulsado@18916, Setup@18986, val2str@18994, MenuCommand@19230, PostInit@19240, Expose@19293

### class jTabla  (49 métodos, 1168 líneas)

Append@16767, BoF@16797, Close@16800, Commit@16816, Data@16821, DBStruct@16824, DefaultValue@16827, EmptyRow@16889, EOF@16951, FIELDGET@16954, FieldPos@16987, FIELDPUT@17020, GoBottom@17023, GoBackward@17038, GoForward@17055, GoTo@17071, GoTop@17121, Init@17141, RecCount@17185, RecNo@17188, RECNO@17191, Seek@17208, Skip@17262, Sort@17303, String2Usual@17340, Usual2String@17389, FieldLen@17445, FieldName@17453, orderkeycount@17461, orderKeygoto@17464, orderkeyno@17467, LASTREC@17470, deleted@17473, EstaEnUnRegistro@17477, Count@17481, FCount@17484, Zap@17487, BorraDesde@17498, Delete@17504, Insert@17525, Subir@17556, Bajar@17572, IndexOrd@17588, SetOrder@17591, symFIELDGET@17594, symFIELDPUT@17627, PonStru@17631, PonDatos@17666, xFIELDPUT@17707

### class jDLV : DATADIALOG  (44 métodos, 1166 líneas)

Init@28743, PantallaCambioAlto@28784, PantallaPonControles@28814, PBBuscar@28846, _Editar@28924, Comando@28952, Terminar@29147, Close@29165, PantallaAncho@29187, PantallaColDefecto@29206, MinLineas@29234, Trabajando@29237, CreaProceso@29240, FinProceso@29247, MinLineasReccount@29252, MaxRegPantalla@29264, PantallaRehacerAncho@29272, expose@29284, PantallaInicio@29301, GridTeclaControl@29345, GridBotonDerecho@29364, GridDobleClick@29372, PantallaAlto@29383, columna@29387, GridTeclaPulsada@29389, ColumnaActiva@29542, siLineaCompleta@29545, SetupAlt@29548, GridPonValor@29576, AyudaBusqueda@29642, show@29651, SetupVideo@29659, Tarea@29750, Dispatch@29756, refresh@29805, GridConfiguracion@29811, MenuCommand@29902, disable@29907, enable@29912, MiraRed@29921, db@29926, ControlB@29930, PulsadoDelete@30068, PulsadoInsert@30073

### class PECalendar : CustomControl  (21 métodos, 886 líneas)

CurrentDate@9147, CurrentDate@9151, Dispatch@9180, Draw3DBox@9293, DrawArrows@9305, DrawDays@9344, DrawOutLine@9485, EditMonth@9528, EditYear@9558, Expose@9602, HighlightDay@9629, Init@9683, KeyDown@9726, MouseButtonDoubleClick@9756, MouseButtonDown@9800, MoveDays@9874, MoveMonths@9902, MoveYears@9938, Show@9967, UnHighlightDay@9973, Setup@10083

### class DatosVideo  (27 métodos, 757 líneas)

Init@10285, AgregaVentana@10311, SituaOrigen@10316, Agrega@10332, PushSecuencia@10362, AgregaGrid@10368, ListaCampos@10395, NumRegs@10431, PopSecuencia@10444, ColocaWindow@10459, Zap@10479, CentraWindow@10489, AgregaShell@10515, ColocaShell@10523, BuscaSecuencia@10560, LeeVideo@10567, TradLista@10613, TradLee@10643, TradGraba@10709, TradEdita@10732, Grabar@10825, CreaVideo@10856, TamMaximoXY@10867, TradDLV@10876, BuscaPosClave@10891, mx@10904, FueraLimites@10908

### class _Class_Registry  (19 métodos, 716 líneas)

LastError@25623, Init@25628, Working_SubKey@25640, hKey@25643, GetString@25646, GetInt@25701, Get_SubKey_ValueNames@25749, Working_SubKey@25819, hKey@25837, LastError@25857, DeleteSubKey@25860, Build_Full_SubKey@25894, CreateSubKey@25926, DeleteValue@25932, Flush@25966, WriteInt@25974, CreateKey@26049, DeleteValueName@26078, WriteString@26086

### class jPrinter  (28 métodos, 650 líneas)

Destroy@21405, ReadDevPar@21416, Start@21443, Stop@21464, OpenPage@21475, ClosePage@21488, Close@21498, Open@21504, Len2Pix@21514, SetMarg@21522, CloseFonts@21530, CloseImages@21541, Imprime@21616, ImprimeSetup@21643, ImprimeCuadro@21690, tam@21763, ImprimeForma@21772, ImprimeTexto@21808, ImprimeX@21837, ImprimeY@21845, DivPalabras@21853, PaintBMP@21880, ImprimeGrafico@21909, ImprimeTextoBloque@21917, Line@21944, FuentePon@21968, FuenteQuita@22004, Init@22011

### class vVisorDlg : DIALOGWINDOW  (18 métodos, 514 líneas)

Init@22588, Destroy@23337, Resize@23345, LeeHojaActual@23428, Imprimir@23792, ImprimirTodo@23889, ImprimirHojaActual@23892, ImprimirSiguientes@23895, ImprimirDeterminadas@23898, PonteEn@23914, expose@24089, MenuCommand@24115, ColocateEn@24123, Comando@24133, MenuAjustar@24189, MenuParcial@24199, Setup@24214, ListaDeterminadas@24281

### class vAvisos : DIALOGWINDOW  (21 métodos, 483 líneas)

Init@24373, Siguiente@24528, Final@24534, Fecha@24539, Eliminar@24552, Cambios@24562, Anterior@24582, PonActual@24739, close@24781, Reponer@24793, MenuCommand@24811, CambiarFechas@24823, EligeMensaje@24861, HacerCambios@24892, Editar@24989, PonSinMensajes@25006, MiraBotones@25019, Dispatch@25086, Nuevo@25107, PostInit@25114, Setup@25164

### class JDDW : DATADIALOG  (17 métodos, 352 líneas)

MenuCommand@14767, expose@14770, NuevaTool@14790, Comando@14798, Ayuda@14916, Close@14924, Trabajando@14936, Activa@14939, Setup@14943, LanzaCalculadora@15028, _Terminar@15038, show@15046, SubMenu@15053, SubMenu@15056, conMensCancelar@15190, Init@15195, QueryClose@15222

### class vAltLista  (11 métodos, 325 líneas)

SetupVideo@14341, GridDobleClick@14455, GridTeclaControl@14464, GridPonValor@14473, GridBotonDerecho@14481, Termina@14487, GridPreguntaColor@14508, GridTeclaPulsada@14516, Setup@14545, Resultado@14624, ButtonClick@14644

### class vPlantillas  (1 métodos, 323 líneas)

GridSiEditamos@11090

### class JServer : dbServer  (13 métodos, 316 líneas)

RegistroACero@1, BorraRegistro@29, RegNuevo@38, SetOrder@56, PopOrder@83, PopOrderRecno@89, Reindexa@153, PonOrden@270, Regenera@280, Close@296, Init@416, FichControl@593, ReindexaUnico@601

### class JDDL : DIALOGWINDOW  (15 métodos, 314 líneas)

MenuCommand@28287, expose@28290, NuevaTool@28310, Comando@28318, Ayuda@28435, Close@28443, Trabajando@28455, Activa@28458, Setup@28462, LanzaCalculadora@28543, _Terminar@28553, show@28561, SubMenu@28568, SubMenu@28571, conMensCancelar@28606

### class vBuscarDLV : DATADIALOG  (10 métodos, 313 líneas)

Init@27783, Cancelar@27870, PostInit@27873, Buscar@27889, ListBoxSelect@27902, Setup2@27921, LeeHistorico@27943, PonHistorico@27968, GrabaHistorico@28016, LimpiarHistorico@28071

### class jPrintExtra  (17 métodos, 290 líneas)

altoDM@20610, anchoDM@20620, cDevice@20629, cNombre@20639, cNombrePapel@20642, cPaperSize@20662, init@20677, Orientation@20715, Orientation@20719, PaperSize@20725, Setup@20732, TiposPapelPDF@20751, aTamDM@20773, aTamDM0@20786, EligePDF@20793, PonPaperSize@20925, PaperSize@20943

### class vJLee : DATADIALOG  (20 métodos, 256 líneas)

Init@5990, Aceptar@6019, MenuCommand@6035, aceptado@6063, PulsadoEscape@6070, expose@6192, PulsadoEnter@6254, cadena@6257, cadena@6260, cancelado@6263, fecha@6266, fecha@6269, numero@6272, picture@6276, valido@6279, posicion@6282, resultado@6285, Setup@6288, fieldspec@6345, Ayuda@6351

### class jPrint : PrintingDevice  (14 métodos, 250 líneas)

cDevice@20288, cDriver@20291, cNombre@20294, cPort@20298, Copias@20302, cNombrePapel@20305, hPrinter@20344, altoDM@20347, anchoDM@20357, aTamDM@20377, aTamDM1@20391, aTamDM0@20405, Orientation@20457, aTamDM2@20523

### class MAPISession  (12 métodos, 246 líneas)

FindFirst@26732, FindNext@26742, Axit@26759, Init@26764, Close@26773, IsOpen@26785, Open@26789, Message@26817, Seed@26821, Message@26828, NewSendCustom@26832, Envia@26923

### class Cardinal  (6 métodos, 242 líneas)

cValor@3353, cBloque@3429, cCentenas@3452, cDecenas@3480, cUnidades@3540, MiraGenero@3579

### class JListView : ListView  (13 métodos, 229 líneas)

Cabeceras@2852, ASeleccionados@2884, TodaLaFila@2897, SetExtendedStyle@2906, Grid@2923, UnSeleccionado@2928, Selecciona@2934, Dispatch@2964, CheckBoxes@2990, NuevoRegistro@2997, BorraCabeceras@3020, XMCabeceras@3074, aMarcados@3088

### class CardinalCatala  (6 métodos, 223 líneas)

cBloque@3838, cCentenas@3861, cDecenas@3873, cValor@3933, MiraGenero@4009, cUnidades@4031

### class clAvisos  (14 métodos, 219 líneas)

Leer@24595, Grabar@24630, Init@24669, Buscar@24675, Dato@24695, Anterior@24698, Siguiente@24716, PonDato@24732, Elimina@24852, nLista@24857, GrabaUno@24993, Ordenar@25054, Lanzar@25143, Mensaje@25310

### class TKTask  (19 métodos, 200 líneas)

IsTask@15245, Init@15265, Create@15279, Axit@15282, CommandLine@15296, ProcessId@15308, TaskName@15311, Title@15316, Commandline@15321, Returncode@15326, TaskId@15330, TaskName@15335, ThreadId@15338, StillRunning@15343, Running@15346, Handle@15349, LaunchFree@15394, nReturncode@15449, LaunchWhile@15485

### class vEAvisos : JDDW  (9 métodos, 196 líneas)

Init@24470, ControlErrores@24951, _GrabaDatos@24962, Setup2@24972, MenuCommand@25096, PostInit@25120, EditFocusChange@25128, Destinatarios@25205, PonDestinatarios@25338

### class oSLECalculadora : SingleLineEdit  (8 métodos, 174 líneas)

Dispatch@19035, Inserta@19091, Borra@19123, Reset@19129, CambiaSigno@19157, Expose@19180, HardReset@19195, BorraCaracter@19204

### class vMensEspera : DIALOGWINDOW  (11 métodos, 172 líneas)

Init@16356, Terminar@16413, Cancelar@16451, PonTotal@16466, Posicion@16473, PostInit@16520, Principal@16541, siCancelado@16603, Texto@16619, PonTotalSec@16721, PosicionSec@16727

### class jIToolbar : jToolbar  (1 métodos, 159 líneas)

init@728

### class docHTM  (21 métodos, 156 líneas)

Axit@1277, Cierra@1282, fw@1296, init@1303, Muestra@1315, Cabecera@1322, fwln@1346, Identar@1350, Lista@1354, ListaElem@1357, CambioTexto@1360, Parrafo@1369, Rotulo@1372, crlf@1382, Encabezado@1392, Tabla@1406, Fila@1409, Celda@1412, Directo@1417, CeldaCabecera@1486, CierraN@1697

### class CardinalEuskera  (6 métodos, 153 líneas)

li@4087, e2@4096, e3@4121, e6@4139, e12@4157, cValor@4177

### class vImagen : DIALOGWINDOW  (6 métodos, 152 líneas)

PostInit@16128, Init@16186, Expose@16201, Close@16249, FileClose@16268, Resize@16272

### class clDefFuente  (6 métodos, 150 líneas)

Texto@20051, Texto@20065, Altura@20224, AlturaEstandar@20234, IgualQue@20255, Load@20548

### class WikFolderDialog : StandardFolderDialog  (9 métodos, 139 líneas)

Init@19485, Show@19488, Caption@19643, Caption@19646, Icon@19649, Icon@19652, Dispatch@19655, __LastPath@19692, __LastPath@19695

### class dlgPECalendar : DIALOGWINDOW  (3 métodos, 137 líneas)

Init@8995, PostInit@9012, Setup@10094

### class vPortapapeles : DATADIALOG  (6 métodos, 136 líneas)

Ayuda@27129, Init@27155, Mensaje@27229, Mensaje@27233, Setup@27238, PostInit@27275

### class MAPIMsg  (19 métodos, 135 líneas)

Subject@26561, DateReceived@26565, NoteText@26574, Subject@26578, Struc2Obj@26582, FileCount@26629, Originator@26633, FullDate@26637, NoteText@26641, ConversationID@26645, MsgID@26649, Init@26653, Axit@26660, TimeReceived@26664, MsgType@26668, AddRecip@26672, RecipCount@26677, RecipList@26681, FileList@26685

### class MDPropCB : ComboBox  (3 métodos, 130 líneas)

Dispatch@13399, SetLock@13466, Init@13471

### class jToolbar : Toolbar  (8 métodos, 123 líneas)

ancho@650, NuevoSeparador@667, Init@672, Nuevo@696, PonTools@707, aNuevo@891, Reinicia@901, Borra@914

### class vPasswordUsuario : JDDWumSLE  (6 métodos, 118 líneas)

Init@5417, _GrabaDatos@5491, ListBoxSelect@5543, Setup1@5558, ButtonClick@5581, PostInit@5611

### class clLL_Base  (5 métodos, 110 líneas)

_CreaBloque@28096, _DameBloque@28106, _GrabaFichero@28118, _LeeFichero@28132, init@28193

### class jDLVsle : SingleLineEdit  (1 métodos, 110 líneas)

Dispatch@28633

### class dlgNewFolder : DIALOGWINDOW  (6 métodos, 106 líneas)

Init@19379, PBOK@19414, PBCancel@19418, FolderName@19421, PostInit@19424, Dispatch@19453

### class vCambiaPassword : JDDWumSLE  (5 métodos, 104 líneas)

Init@5142, ControlErrores@5199, _GrabaDatos@5262, Setup1@5266, PostInit@5605

### class FicheroTXT  (10 métodos, 103 líneas)

close@1727, EOF@1734, init@1737, leer@1745, escribir@1751, write@1762, writeln@1768, readln@1773, Axit@1806, CreaDBmemo@1810

### class clINI  (6 métodos, 96 líneas)

CreaBloque@1546, DameBloque@1556, GrabaFichero@1568, init@1581, LeeClave@1590, LeeFichero@1601

### class vjBuscar : DIALOGWINDOW  (7 métodos, 92 líneas)

Init@15791, Terminar@15820, PostInit@15823, expose@15831, Close@15845, Buscar@15851, Dispatch@15867

### class vAnchoAlto : DIALOGWINDOW  (3 métodos, 88 líneas)

aceptar@20837, PostInit@20846, Init@20889

### class MDPropSLE : MathiasSLE  (3 métodos, 87 líneas)

Dispatch@13244, Init@13306, SetLock@13323

### class clLL_Bloque  (6 métodos, 81 líneas)

init@28206, ListaClavesValores@28211, PonNombre@28223, PonValor@28227, Texto@28263, V@28276

### class jServer  (10 métodos, 75 líneas)

CreaIndiceCDX@109, SoloLectura@303, append@307, FIELDPUT@314, SoloLectura@322, LogDefines@325, MuestraEstado@341, MarcaRI@507, RecuperaRI@511, EstaEnUnRegistro@646

### class jserver  (1 métodos, 73 líneas)

CompruebaFD@197

### class clMensAvisos  (5 métodos, 73 líneas)

Graba@25258, init@25276, Lee@25287, siUsuario@25304, cListaUsuarios@25317

### class vJMemo : DATADIALOG  (3 métodos, 72 líneas)

Init@6101, Setup@6123, MenuCommand@6160

### class clDefTexto  (4 métodos, 72 líneas)

Texto@19956, codTexto@19974, decodTexto@19990, Texto@20008

### class MarcaPosicion  (3 métodos, 70 líneas)

init@523, Marca@531, Recupera@541

### class vAdvierte : DIALOGWINDOW  (4 métodos, 68 líneas)

Init@10127, Seguir@10169, Cancelar@10174, PostInit@10191

### class vLeeFecha : DATADIALOG  (6 métodos, 66 líneas)

Init@5675, Setup@5711, Aceptar@5717, fecha@5740, Escape@5743, PostInit@5901

### class JDDWumSLE : JDDWsinRed  (3 métodos, 64 líneas)

LaPrimeraVez@15064, PulsadoEscape@15083, PulsadoEnter@15144

### class logging  (6 métodos, 61 líneas)

Init@4264, Escribe@4282, Axit@4288, Cierra@4291, Var@4312, VarArray@4325

### class clInfo  (5 métodos, 61 líneas)

init@6759, Mas@6768, Pop@6785, Valor@6793, Menos@6804

### class clDefSetup  (5 métodos, 59 líneas)

Texto@20096, Texto@20106, masGraficos@20119, codGraficos@20128, decodGraficos@20139

### class RTFtxt  (3 métodos, 57 líneas)

init@1220, TXTenRTF@1227, RTFenTXT@1245

### class clINI_Bloque  (6 métodos, 55 líneas)

DameValor@1642, init@1653, PonNombre@1656, PonValor@1659, PosClave@1680, Texto@1684

### class cadBin64  (5 métodos, 55 líneas)

Activa@3644, aLista@3652, init@3668, LeeTexto@3677, Texto@3686

### class Procesando : DIALOGWINDOW  (4 métodos, 51 líneas)

Init@15467, Setup@15494, Dispatch@15500, Cancelar@15519

### class vMensCancelar : DIALOGWINDOW  (4 métodos, 47 líneas)

Init@16650, SI@16694, NO@16698, PostInit@16702

### class TreeView  (1 métodos, 43 líneas)

GetChildItem@5947

### class vTrad : jDLV  (5 métodos, 39 líneas)

Borra@10669, columna@10686, GridPonValor@10690, GridConfiguracion@10705, Edita@10852

### class MAPIFile : FileSpec  (1 métodos, 37 líneas)

Init@26524

### class ListaNumeros  (7 métodos, 36 líneas)

init@3144, nuevo@3155, cerrar@3159, numero@3163, zap@3167, elementos@3170, Axit@3220

### class MAPIRecip  (5 métodos, 36 líneas)

Name@26696, Address@26700, Name@26704, Address@26708, Init@26712

### class DLVConfDefecto  (2 métodos, 35 líneas)

PorDefecto@29607, PonTipoLetra@29634

### class DatosFichero  (2 métodos, 33 líneas)

init@2534, Lee@2538

### class MLENotas : MultiLineEdit  (1 métodos, 31 líneas)

Dispatch@6356

### class clDefGrafico  (2 métodos, 31 líneas)

Texto@19921, Texto@20028

### class umSLE : MathiasSLE  (1 métodos, 30 líneas)

Dispatch@15114

### class TablaNumeros  (7 métodos, 29 líneas)

Axit@3604, cerrar@3609, elementos@3612, init@3615, nuevo@3624, numero@3627, zap@3630

### class clDefLinea  (2 métodos, 27 líneas)

Texto@19929, Texto@19940

### class MiraMemo  (2 métodos, 26 líneas)

init@1064, Elemento@1083

### class jListView  (1 métodos, 26 líneas)

GetColumnAtPosition@3048

### class jDDW  (1 métodos, 26 líneas)

Dispatch@15088

### class jDDL  (1 métodos, 26 líneas)

Dispatch@28574

### class FE3N : FIELDSPEC  (1 métodos, 25 líneas)

Init@25471

### class mathiasSle  (1 métodos, 24 líneas)

Calculadora@8810

### class jGridVSBAR : VerticalScrollBar  (1 métodos, 21 líneas)

Dispatch@14119

### class oGridCalculadora : jGridE  (1 métodos, 21 líneas)

PonBien@19136

### class clDefFirmaDigital : clDefGrafico  (1 métodos, 21 líneas)

Texto@20589

### class jTablaNum : jTabla  (4 métodos, 20 líneas)

init@17687, Numero@17693, Elementos@17697, Nuevo@17702

### class FE10_2 : FIELDSPEC  (1 métodos, 20 líneas)

Init@25582

### class SLEMiraEnterPass : SingleLineEdit  (1 métodos, 17 líneas)

Dispatch@5285

### class vALtLista : DIALOGWINDOW  (1 métodos, 17 líneas)

Init@14324

### class vALtListaH  (1 métodos, 17 líneas)

Init@14708

### class SLEMiraEnter : MathiasSLE  (1 métodos, 16 líneas)

Dispatch@8935

### class vPortaPapeles  (5 métodos, 16 líneas)

Cancelar@27139, CopAsunto@27143, CopDestino@27146, CopFichero@27149, CopMensaje@27152

### class C20m : FIELDSPEC  (1 métodos, 15 líneas)

Init@25433

### class C40m : FIELDSPEC  (1 métodos, 15 líneas)

Init@25448

### class FE13N : FIELDSPEC  (1 métodos, 15 líneas)

Init@25553

### class FE5_2 : FIELDSPEC  (1 métodos, 12 líneas)

Init@25382

### class FE2N : FIELDSPEC  (1 métodos, 12 líneas)

Init@25394

### class FE4N : FIELDSPEC  (1 métodos, 12 líneas)

Init@25496

### class FE8N : FIELDSPEC  (1 métodos, 12 líneas)

Init@25508

### class FE2N0 : FIELDSPEC  (1 métodos, 12 líneas)

Init@25528

### class d8 : FIELDSPEC  (1 métodos, 11 líneas)

Init@5729

### class jGridPushButton : PushButton  (1 métodos, 9 líneas)

Dispatch@14147

### class FE6_2 : FIELDSPEC  (1 métodos, 9 líneas)

Init@25406

### class C128 : FIELDSPEC  (1 métodos, 9 líneas)

Init@25573

### class C24 : FIELDSPEC  (1 métodos, 9 líneas)

Init@25609

### class BMPToolImprimir : Bitmap  (1 métodos, 8 líneas)

Init@16085

### class C15m : FIELDSPEC  (1 métodos, 8 líneas)

Init@25425

### class C64m : FIELDSPEC  (1 métodos, 8 líneas)

Init@25463

### class C1m : FIELDSPEC  (1 métodos, 8 líneas)

Init@25520

### class C5N : FIELDSPEC  (1 métodos, 8 líneas)

Init@25540

### class BMPTOOLBAR_CARLO1 : Bitmap  (1 métodos, 7 líneas)

Init@941

### class CPass : FIELDSPEC  (1 métodos, 7 líneas)

Init@5278

### class BMPCadena : BitMap  (1 métodos, 7 líneas)

Init@15895

### class BMPCalculadora : Bitmap  (1 métodos, 7 líneas)

Init@15932

### class BMPCambiar : Bitmap  (1 métodos, 7 líneas)

Init@15939

### class BMPd : Bitmap  (1 métodos, 7 líneas)

Init@15946

### class BMPEscribe : Bitmap  (1 métodos, 7 líneas)

Init@15953

### class BMPImpresora : Bitmap  (1 métodos, 7 líneas)

Init@15960

### class BMPInsertar : Bitmap  (1 métodos, 7 líneas)

Init@15967

### class BMPInterrogante : Bitmap  (1 métodos, 7 líneas)

Init@15974

### class BMPPeligro : Bitmap  (1 métodos, 7 líneas)

Init@15981

### class BMPRegAnterior : Bitmap  (1 métodos, 7 líneas)

Init@15988

### class BMPRegPrimero : Bitmap  (1 métodos, 7 líneas)

Init@15995

### class BMPRegSiguiente : Bitmap  (1 métodos, 7 líneas)

Init@16002

### class BMPUnoMas : Bitmap  (1 métodos, 7 líneas)

Init@16009

### class BMPUnoMenos : Bitmap  (1 métodos, 7 líneas)

Init@16016

### class BMPRegUltimo : Bitmap  (1 métodos, 7 líneas)

Init@16023

### class BMPCancelar : Bitmap  (1 métodos, 7 líneas)

Init@16030

### class BMPEuro : Bitmap  (1 métodos, 7 líneas)

Init@16037

### class BMPNuevo : Bitmap  (1 métodos, 7 líneas)

Init@16044

### class BMPOriApaisado : Bitmap  (1 métodos, 7 líneas)

Init@16051

### class BMPOriNormal : Bitmap  (1 métodos, 7 líneas)

Init@16058

### class BMPPantalla : Bitmap  (1 métodos, 7 líneas)

Init@16065

### class ICOLibreta : Icon  (1 métodos, 7 líneas)

Init@16072

### class BMPGiro : Bitmap  (1 métodos, 7 líneas)

Init@16117

### class C4M : FIELDSPEC  (1 métodos, 7 líneas)

Init@25351

### class C64 : FIELDSPEC  (1 métodos, 7 líneas)

Init@25375

### class C24IBAN : FIELDSPEC  (1 métodos, 7 líneas)

Init@25602

### class Class_HKCR : _Class_Registry  (1 métodos, 7 líneas)

Init@25887

### class JDDWsinRed : JDDW  (2 métodos, 6 líneas)

Bloquea@15184, desBloquea@15187

### class BMPMas : BitMap  (1 métodos, 6 líneas)

Init@15883

### class BMPMenos : BitMap  (1 métodos, 6 líneas)

Init@15889

### class BMPABAJO  (1 métodos, 6 líneas)

Init@15902

### class BMPAbajoFinal : Bitmap  (1 métodos, 6 líneas)

Init@15908

### class BMPArriba : Bitmap  (1 métodos, 6 líneas)

Init@15914

### class BMPArribaInicio : Bitmap  (1 métodos, 6 líneas)

Init@15920

### class BMPBuscar : Bitmap  (1 métodos, 6 líneas)

Init@15926

### class BMPToolTerminar : Bitmap  (1 métodos, 6 líneas)

Init@16079

### class ICOCALC : Icon  (1 métodos, 6 líneas)

Init@16093

### class ICOCALCPEQUE : Icon  (1 métodos, 6 líneas)

Init@16099

### class BMPMASPQ : Bitmap  (1 métodos, 6 líneas)

Init@16105

### class MGDV : Icon  (1 métodos, 6 líneas)

Init@16111

### class C30 : FIELDSPEC  (1 métodos, 6 líneas)

Init@25358

### class C30m : FIELDSPEC  (1 métodos, 6 líneas)

Init@25364

### class JDDLsinRed : JDDL  (2 métodos, 6 líneas)

Bloquea@28600, desBloquea@28603

### class BMPTOOLBAR : Bitmap  (1 métodos, 5 líneas)

Init@723

### class fsTrad : FIELDSPEC  (1 métodos, 5 líneas)

Init@10700

### class C40 : FIELDSPEC  (1 métodos, 5 líneas)

Init@25370

### class C20 : FIELDSPEC  (1 métodos, 5 líneas)

Init@25415

### class C20n : FIELDSPEC  (1 métodos, 5 líneas)

Init@25420

### class C3M : FIELDSPEC  (1 métodos, 5 líneas)

Init@25548

### class C128m : FIELDSPEC  (1 métodos, 5 líneas)

Init@25568

### class C11m : FIELDSPEC  (1 métodos, 5 líneas)

Init@25618

### class Class_HKLM : _Class_Registry  (1 métodos, 5 líneas)

Init@25877

### class Class_HKCU : _Class_Registry  (1 métodos, 5 líneas)

Init@25882

### class ITOOLBAR : Bitmap  (1 métodos, 4 líneas)

Init@887

### class TreeViewItem  (1 métodos, 4 líneas)

Numero@5921

### class vAltListaH : DataWindow  (1 métodos, 4 líneas)

MenuCommand@14704

### class BMPInfo : Bitmap  (1 métodos, 4 líneas)

Init@16124

### class ICARLO16 : Bitmap  (1 métodos, 3 líneas)

Init@948

### class ICOIMPRE : Icon  (1 métodos, 3 líneas)

Init@16313

### class IJDD : Icon  (1 métodos, 3 líneas)

Init@29412

### funciones/procedimientos sueltos (291)

aDBF2Array@96(13), CreaDefines@118(18), DBFTemporalBase@136(4), BorraCDX@140(4), DBF2CDX@144(9), Array2DBF@349(8), AbreDBF@357(41), AbreDBFDudoso@398(18), aDivPalabras@951(20), cPeina@971(9), SoloNumLetras@980(19), C3Mas@999(36), NumeroC4@1035(21), PrimeraMayuscula@1056(8), aLineasGraficas@1090(10), Transforma@1100(120), DToTxt@1403(3), aDivPalabras2@1420(18), esSoloNumeros@1438(14), SoloNumLetrasEspacios@1452(20), PrimeraLinea@1472(14), PrimeraMayuscula1@1491(4), aDivBloques@1495(51), jMemoWrite@1708(19), lSobreescribir@1830(9), cPideFichero@1839(63), cNomFichero@1902(18), BorraFichero@1920(14), CopiaFichero@1934(32), FilePath@1966(11), BorraDiscoA@1977(3), BorraDirectorio@1980(21), FicheroTemporalBase@2001(19), RenombraFichero@2020(10), GetSpecialFolder@2030(223), BorraTMP@2253(3), BorraDirExt@2256(9), DiscoSinProteccion@2265(17), cPideFicheroDBF@2282(10), BienNomFichero@2292(14), SHCopy@2306(39), MueveFichero@2345(19), ErrorHandler@2364(5), HazDirectorio@2369(11), ExpandeFichero@2380(42), MismoFichero@2422(3), QuitaAtributos@2425(6), SHRename@2431(39), FEraseWin@2470(16), BorraFicheroWin@2486(15), BorraDirectorioWin@2501(33), TamFichero@2567(13), QuitaProteccionDir@2580(23), EsSoloLectura@2603(9), cPideImagen@2612(49), ExisteDirectorio@2661(10), lDirConFicheros@2671(16), mdGetFile@2687(59), proporcionBMP@2746(50), FechaFichero@2796(7), BorraFicheros@2803(10), BienNomFichero1@2813(16), ComparaFechaFicheros@2829(23), EsCero3@3107(3), EvaluaCadena@3110(34), EuroPts@3173(4), PtsEuro@3177(13), EsDistinto3@3190(3), EsIgual3@3193(4), NTrimInterno@3197(7), cPNumero0@3204(8), Monedas@3212(5), cNTrim@3217(3), EsNumero@3227(14), PonDec@3241(25), PonnDecimalesLim@3266(28), EsCero@3294(3), cPNumero@3297(23), cPNumeroDec@3320(21), NoCero3@3341(12), NumeroEnLetras@3570(9), siEntreDos@3633(3), EsNegativo3@3636(8), CadenaNumerosSiEsta@3699(28), CadenaNumerosLee@3727(57), CadenaNumerosCad2Array@3784(54), NumeroEnLetrasCatalan@4061(9), EsPositivo3@4070(3), ValPuntos@4073(14), NumeroEnLetrasEuskera@4240(9), FueraLimites@4249(9), NoCasiCero3@4258(6), AbreLog@4299(3), CierraLog@4302(4), EscribeLog@4306(6), dGasta@4338(14), MiraStack@4352(26), MiraDebugShell@4378(4), MiraMemoria@4382(18), AbreDebug@4400(3), CierraDebug@4403(2), PonDebugIni@4405(16), DBG@4421(13), DBGDispatchH@4434(4), DBGDispatch@4438(4), DBGH@4442(19), timeXM@4461(21), LogmXM@4482(26), glis_dispatch0@4508(32), glis_inicio@4540(192), glis_xm@4732(4), lXM@4736(40), LogXM@4776(21), conXM@4797(20), VarXM@4817(13), VarArrayXM@4830(188), XM@5018(34), Desencripta@5052(90), aCambiaPassword@5224(16), Encripta@5240(22), Encrypt@5302(39), Decrypt@5341(76), LeePasswordUsuario@5479(12), RotuloArr@5495(22), RotuloPG@5517(14), RotuloTit@5531(12), RotuloDLL@5587(8), RotuloFD@5595(10), LeeFecha@5619(10), PrimerDiaMes@5629(4), UltimoDiaMes@5633(13), FullDate@5646(29), cMes@5746(3), SumaMeses@5749(34), Semana@5783(22), EvaluaCadenaFecha@5805(68), _TFechas@5873(18), cDia@5891(10), SumaMesesFM@5907(14), IsChildOf@5925(22), LeeMemo@6173(19), LeeTexto@6235(19), NombreFuentesStandard@6387(20), mdGetFontList@6407(33), __EnumFntProc@6440(7), AssignFont@6447(20), EligePrintFont@6467(39), mdChooseWinFont@6506(33), LoadWinFontStd@6539(51), LoadWinFont@6590(41), CreaListaFuentes@6631(28), siExisteFuente@6659(14), DameUnaFuenteCualquiera@6673(32), gR_Limpia@6705(3), gR_ConDatos@6708(13), _CopiarPegarPush@6721(38), LanzaAyuda@6820(7), SinAyuda@6827(31), LanzaMenuUno@6858(69), SLEPrimero@6927(5), Ejecuta@6932(22), FabFilterMessages@6954(22), PonMenuPeligro@6976(74), invRGB@7050(25), LanzaMenuOpcionUltima@7075(15), CambiaColor@7090(18), Mouseclick@7108(14), _EnumWinFunc@7122(9), ListWindowsTitles@7131(21), LanzaMenu@7152(25), PonCursor@7177(34), VisualizaShell@7211(10), NumComandos@7221(7), LeeComando@7228(7), aLineaComandos@7235(32), aKill@7267(5), aBusca2@7272(10), aBusca@7282(12), aBusca2dh@7294(9), Array2String@7303(45), String2Array@7348(61), IsEditTemplChar@7409(15), IsOverWriteModeEnabled@7424(7), with@8706(74), MoveTo@9099(48), FirstDayOfWeek@10022(4), IsLeapYear@10026(19), MiDow@10045(6), PointInSide@10051(21), GetMonth@10072(11), Advierte@10178(13), CompruebaPosWindow@10208(22), MiraPosWindow@10230(9), PonPosWindow@10239(46), CentraCursor@10485(4), SysRefreshMsg@13230(14), ignores@13529(4), vtDarkColor@13533(20), __SendKey@13800(19), AltListaMultiple@14666(15), AltListaMultipleEx@14681(23), AltLista@14725(13), AltListaSimple@14738(29), dummy@15363(2), LastProcErrorAsText@15365(29), ConvertFindData@15527(33), dwAttribute2String@15560(44), FileAttributeOK@15604(45), ExtendedDirectory@15649(92), UTC2DateTime@15741(50), zDIBLeePTR@16280(33), MuestraError@16316(40), FinMensEspera@16424(6), Mensaje@16430(5), lMira@16435(13), Pregunta@16448(3), MensEsperaCancelado@16458(8), MensEspera@16490(15), MensEsperaPosicion@16505(10), MensEsperaTexto@16515(5), MensEsperaPrincipal@16532(9), MuestraErrorF@16547(14), CambioMensEspera@16561(19), MensEsperaTotal@16580(23), PreguntaCancelar@16607(12), MensCancelar@16683(11), MensEsperaTotalSec@16708(13), MensEsperaPosicionSec@16741(26), LanzaCalculadora@19345(34), WikFolderDialog_BrowseCallbackProc@19551(92), WikFolderDialog_DialogProc@19716(36), WikFolderDialog_OnNewFolder@19752(29), EligeDirectorio@19781(23), CenterWindow@19804(22), CheckPath@19826(14), ConvierteIMG2BMP@19840(81), Ordenes2Memo@20155(19), Memo2Ordenes@20174(50), CreaDBhoja@20367(10), prtW2Pix@20988(4), prtL2Pix@20992(3), WriteText@20995(83), FilledRect@21078(63), ImprimeTextoUno@21141(35), ImprimeTextoJustificado@21176(55), EmptyRect@21231(54), ImprimeTextoFrase@21285(81), ImprimeHojas@21366(39), EmptyRect@22055(65), WriteText@22120(102), FilledRect@22222(85), MuestraTextoUno@22307(34), MuestraTextoJustificado@22341(54), mdrgPaintBmp@22395(27), mdrgLoadBMP@22422(49), MuestraTextoFrase@22471(80), rpvL2Scale@22551(8), rpvW2Pix@22559(29), MirarAvisos@25157(7), IsMAPIAvailable@26356(36), MAPIFreeBuffer@26392(11), _MAPIInit@26403(30), _MAPIExit@26433(7), MAPILogon@26440(22), MAPIFindNext@26462(23), MAPISendMail@26485(39), MAPIEnvia@26908(15), MAPILogoff@26993(18), MAILEnvia@27011(29), MAILEnviaFoxmail@27040(17), MAILEnviaYOQUESE@27057(17), Portapapeles@27074(8), CopyTexto@27082(47), siMAILOutlook@27281(11), _1@27292(4), _@27296(53), _2@27349(4), _3@27353(5), _W@27358(39), _RehazPO@27397(82), _leeGT@27479(41), xnum@27520(23), xnum1@27543(35), CRCSetPolynom@27578(10), spCRCShiftArray@27588(20), spCRCGetBit@27608(16), CRCGenerate@27624(38), ControlFichero@27662(61), CRCFichero@27723(60), Setupa@29415(127), Setup@29571(5)

## B_Zip  (6907 líneas)


### class FabZipFile  (75 métodos, 2955 líneas)

Init@3953, FileName@3996, FileName@4001, ZipDLLVersion@4015, UnZipDLLVersion@4020, FilesCount@4025, Processing@4030, Trace@4035, Trace@4040, Verbose@4048, Verbose@4053, Owner@4061, Owner@4066, FilesArg@4075, FilesArg@4084, FilesOperated@4235, Extract@4240, ExtractDir@4386, ExtractDir@4391, Copy@4400, Success@4408, UpdateContents@4413, Delete@4586, CodePage@4725, CodePage@4732, __ConvertCodePage@4754, __EraseFile@4800, __IsDiskPresent@4837, ZipComment@4904, ErrCode@4912, Message@4916, ZipBusy@4920, UnzBusy@4925, __CheckForDisk@4930, __IsRightDisk@5000, __GetNewDisk@5021, __ShowZipMessage@5060, __LoadZipStr@5080, __ShowExceptionError@5091, __SetZipParams@5109, __SetUnZipParams@5226, __RWCentralDir@5302, __DiskFreeAndSize@5353, __WriteSpan@5365, __WriteSplit@5585, __ReadSpan@5749, __AllocSpanMem@6031, __DeleteSpanMem@6043, __FindZipEntry@6055, __WriteJoin@6080, __RWSplitData@6094, __RWJoinData@6116, __ZipFormat@6139, __CheckIfLastDisk@6147, MadeByVersion@6286, HostVersionNo@6292, Password@6316, Password@6321, DeleteCanUndo@6326, DeleteCanUndo@6332, Add@6338, CompressionLevel@6528, CompressionLevel@6533, Contents@6548, MaxVolumeSize@6553, MaxVolumeSize@6561, MinFreeVolumeSize@6569, MinFreeVolumeSize@6577, KeepFreeOnDisk1@6585, KeepFreeOnDisk1@6592, TempDir@6599, TempDir@6609, Unattended@6619, Unattended@6623, LastWrittenFile@6628

### class FabFileBin  (51 métodos, 687 líneas)

Init@1501, Handle@1519, Axit@1524, Close@1531, Commit@1545, Create@1558, ReadBlock@1581, ReadLine@1597, ReadStr@1612, ReadText@1625, Rewind@1640, Seek@1650, IsOpen@1670, CopyFrom@1675, ReadBuffer@1704, WriteBuffer@1723, UpdateError@1743, Destroy@1748, EOF@1753, Error@1766, ErrorCode@1771, ErrString@1776, FileHandle@1792, FileSpec@1797, GoBottom@1802, GoTo@1810, GoTop@1818, Open@1826, Position@1842, Read@1847, Tell@1871, Write@1883, WriteBlock@1903, WriteLine@1922, WriteText@1941, Size@1960, Position@1965, ReadLong@1973, ReadDWord@1982, ReadShort@1991, ReadWord@2000, ReadByte@2009, _UpdateSize@2018, Exist@2030, __GetDateTime@2035, __SetDateTime@2056, __SetDateTime2@2079, DateChanged@2089, DateChanged@2099, TimeChanged@2131, TimeChanged@2140

### class ProcesaZip : FabZipFile  (14 métodos, 516 líneas)

Ejecuta@135, Comprime@157, Extrae@183, Testea@214, Handle@234, OnFabZipProgress@237, OnFabZipDirUpdate@254, OnFabZipMessage@257, init@264, Comando@275, Informe@278, LeeFicheroControl@287, SinErrores@309, Extra@312

### class FabArray  (37 métodos, 391 líneas)

Add@1030, Contents@1044, Contents@1049, Current@1067, Current@1076, DeleteCurrent@1088, GoBottom@1104, GoTop@1111, Init@1120, PastBottom@1131, Seek@1136, SkipNext@1146, SkipPrevious@1151, Skip@1156, Size@1189, Len@1194, Del@1198, Get@1214, Pos@1224, GoTo@1229, Delete@1244, Append@1249, EOF@1262, BOF@1267, PastTop@1272, Zap@1277, Put@1287, FillUsing@1299, Clear@1315, Ins@1330, Insert@1358, Empty@1363, Replace@1368, SET@1382, ScanExact@1394, Sort@1404, Scan@1411

### class FabFormatDialog  (4 métodos, 207 líneas)

Init@2188, Show@2214, LastReturnCode@2283, Success@2382

### class FabZipDirEntry  (20 métodos, 155 líneas)

Version@3772, Flag@3777, CompressionMethod@3781, CRC32@3799, CompressedSize@3804, UncompressedSize@3809, FileNameLength@3814, ExtraFieldLength@3818, FileName@3822, Init@3827, FileTime@3849, FileDate@3854, Ratio@3859, Crypted@3864, DateTime@3869, StartOnDisk@3873, FileComment@3879, IntFileAttrib@3884, ExtFileAttrib@3890, Attributes@3896

### class FabAddOptions  (22 métodos, 149 líneas)

Freshen@3500, Move@3505, Update@3510, Freshen@3515, Move@3524, Update@3533, DiskSpan@3557, DiskSpan@3562, DiskSpanErase@3573, DiskSpanErase@3578, DirNames@3589, DirNames@3594, SeparateDirs@3605, SeparateDirs@3610, RecurseDirs@3621, RecurseDirs@3626, ZipTime@3631, ZipTime@3636, ForceDos@3641, ForceDos@3646, System@3653, System@3658

### class FabError : Error  (3 métodos, 80 líneas)

_Raise@1421, _Break@1451, Raise@1462

### class FabExtractOptions  (10 métodos, 67 líneas)

Update@3542, Freshen@3552, Freshen@3664, Test@3673, Test@3680, Update@3691, OverWrite@3696, OverWrite@3701, DirNames@3706, DirNames@3711

### class FabZipFileError : FabError  (1 métodos, 26 líneas)

Init@3927

### funciones/procedimientos sueltos (37)

mgdFabZip@1(43), Mens_TR@44(91), FabZCallBackSample@651(379), FabPackedWord2Time@2395(14), FabPackedWord2Date@2409(17), FabDate2PackedWord@2426(26), FabTime2PackedWord@2452(19), Fabatoi@2471(26), FabFormatCString@2497(222), FabLoadStr@2719(29), FabExtractFileDrive@2748(38), FabExtractFileExt@2786(24), FabExtractFileName@2810(27), FabGetDiskFree@2837(18), FabGetSystemDir@2855(15), FabGetWindowsDir@2870(15), FabIsDir@2885(25), FabCursorArrow@2910(11), FabCursorWait@2921(11), FabGetDiskSize@2932(18), FabGetTempFile@2950(29), FabExtractFilePath@2979(23), FabMemCopyString@3002(12), FabPszCopy@3014(40), FabConcatDir@3054(43), FabGetFileDateTime@3097(28), FabGetTempPath@3125(25), FabGetLogicalDrivesArray@3150(51), FabSetDiskLabel@3201(22), FabAdd2Ptr@3223(43), FabIsDiskReady@3266(12), FabGetDiskLabel@3278(46), FabStripJunkFromString@3324(13), FabZCallback@3337(163), FabAppendSlash@3716(11), FabReplaceForwardSlash@3727(5), FabDiskSize@3732(40)

## C_Datos  (9430 líneas)


### class fArticulos : jServer  (64 métodos, 542 líneas)

init@5779, ListaCampos@5799, NUMERO@5838, NUMERO@5848, CODIGO@5851, CODIGO@5861, EAN13@5864, EAN13@5874, UBICACION@5877, UBICACION@5887, PROVEEDOR@5890, PROVEEDOR@5900, FAMILIA@5903, FAMILIA@5913, NOMBRE@5916, NOMBRE@5926, PVENTA@5929, PVENTA@5939, PVENTAIVA@5942, PVENTAIVA@5952, DCTO@5955, DCTO@5965, TDCTO@5968, TDCTO@5978, DCTO2@5981, DCTO2@5991, DCTO3@5994, DCTO3@6004, PCOMPRA@6007, PCOMPRA@6017, PCDCTO@6020, PCDCTO@6030, PCDCTO2@6033, PCDCTO2@6043, PCDCTO3@6046, PCDCTO3@6056, TIPOIVAC@6059, TIPOIVAC@6069, TIPOIVAV@6072, TIPOIVAV@6082, OPERACIONC@6085, OPERACIONC@6095, OPERACIONV@6098, OPERACIONV@6108, ALBINVENT@6111, ALBINVENT@6121, FINVENT@6124, FINVENT@6134, QINVENT@6137, QINVENT@6147, QCOMPRAS@6150, QCOMPRAS@6160, QVENTAS@6163, QVENTAS@6173, MINIMO@6176, MINIMO@6186, TIPO@6189, TIPO@6199, MARCA@6202, MARCA@6212, ASOCIADO@6215, ASOCIADO@6225, NOTAS@6228, NOTAS@6241

### class fClientes : jServer  (58 métodos, 491 líneas)

init@1033, ListaCampos@1047, NUMERO@1083, NUMERO@1093, NOMBRE@1096, NOMBRE@1106, COMERCIAL@1109, COMERCIAL@1119, DOMICILIO@1122, DOMICILIO@1132, LOCALIDAD@1135, LOCALIDAD@1145, PROVINCIA@1148, PROVINCIA@1158, COD_POSTAL@1161, COD_POSTAL@1171, AP_CORREOS@1174, AP_CORREOS@1184, NIF@1187, NIF@1197, CUENTA@1200, CUENTA@1210, OPERACION@1213, OPERACION@1223, BRUTO@1226, BRUTO@1236, NETO@1239, NETO@1249, PENDIENTE@1252, PENDIENTE@1262, BANCO_NOM@1265, BANCO_NOM@1275, BANCO_SUC@1278, BANCO_SUC@1288, BANCO_DIG@1291, BANCO_DIG@1301, MANDATO@1304, MANDATO@1314, F_MANDATO@1317, F_MANDATO@1327, BIC@1330, BIC@1340, IVA@1343, IVA@1353, BANCO_TIT@1356, BANCO_TIT@1366, ANTICIPO@1369, ANTICIPO@1379, TIPO@1382, TIPO@1392, DECLTERC@1395, DECLTERC@1405, MARCA@1408, MARCA@1418, CONTACTOS@1421, CONTACTOS@1434, NOTAS@1437, NOTAS@1450

### class fProveedores : jServer  (48 métodos, 414 líneas)

init@619, ListaCampos@633, NUMERO@664, NUMERO@674, NOMBRE@677, NOMBRE@687, COMERCIAL@690, COMERCIAL@700, DOMICILIO@703, DOMICILIO@713, LOCALIDAD@716, LOCALIDAD@726, PROVINCIA@729, PROVINCIA@739, COD_POSTAL@742, COD_POSTAL@752, AP_CORREOS@755, AP_CORREOS@765, NIF@768, NIF@778, CUENTA@781, CUENTA@791, OPERACION@794, OPERACION@804, BRUTO@807, BRUTO@817, PENDIENTE@820, PENDIENTE@830, NETO@833, NETO@843, IVA@846, IVA@856, CTAIRPF@859, CTAIRPF@869, ANTICIPO@872, ANTICIPO@882, TIPO@885, TIPO@895, CCAJA@898, CCAJA@908, DECLTERC@911, DECLTERC@921, MARCA@924, MARCA@934, CONTACTOS@937, CONTACTOS@950, NOTAS@953, NOTAS@966

### class fInfapun : jServer  (46 métodos, 383 líneas)

init@4091, ListaCampos@4101, INFORME@4131, INFORME@4141, NUMERO@4144, NUMERO@4154, PADRE@4157, PADRE@4167, TEXTO@4170, TEXTO@4180, TIPO@4183, TIPO@4193, MODO_IMP@4196, MODO_IMP@4206, LINEA_SEP@4209, LINEA_SEP@4219, LINEA_DEB@4222, LINEA_DEB@4232, LINEA_ENC@4235, LINEA_ENC@4245, CONDICION@4248, CONDICION@4258, MARGEN_TXT@4261, MARGEN_TXT@4271, MARGEN_IMP@4274, MARGEN_IMP@4284, ALIN_TXT@4287, ALIN_TXT@4297, ALIN_IMP@4300, ALIN_IMP@4310, CLAVE@4313, CLAVE@4323, DECIMALES@4326, DECIMALES@4336, SUMAR@4339, SUMAR@4349, NEGRITA@4352, NEGRITA@4362, HABER@4365, HABER@4375, PORC@4378, PORC@4388, TIPOSAS@4391, TIPOSAS@4401, DATOS@4404, DATOS@4417

### class fApuntes : jServer  (44 métodos, 367 líneas)

init@6731, ListaCampos@6743, ALBARAN@6772, ALBARAN@6782, TALBARAN@6785, TALBARAN@6795, FECHA@6798, FECHA@6808, TIPO@6811, TIPO@6821, ARTICULO@6824, ARTICULO@6834, TEXTO@6837, TEXTO@6847, TEXTO2@6850, TEXTO2@6860, TEXTO3@6863, TEXTO3@6873, DCTO1@6876, DCTO1@6886, DCTO2@6889, DCTO2@6899, DCTO3@6902, DCTO3@6912, CANTIDAD@6915, CANTIDAD@6925, PRECIO@6928, PRECIO@6938, IMPORTE@6941, IMPORTE@6951, PVENTAIVA@6954, PVENTAIVA@6964, TIVA@6967, TIVA@6977, TIPOOP@6980, TIPOOP@6990, CUENTA@6993, CUENTA@7003, REPARTO@7006, REPARTO@7016, GRUPO@7019, GRUPO@7029, ALMACEN@7032, ALMACEN@7042

### class fRecibidas : jServer  (42 métodos, 365 líneas)

init@3062, ListaCampos@3081, NUMERO@3109, NUMERO@3119, CNUMERO@3122, CNUMERO@3132, TIPONUM@3135, TIPONUM@3145, CNUMALT@3148, CNUMALT@3158, FECHA@3161, FECHA@3171, REGFECHA@3174, REGFECHA@3184, PROVEEDOR@3187, PROVEEDOR@3197, PRCUENTA@3200, PRCUENTA@3210, PRFACTURA@3213, PRFACTURA@3223, PRFECHA@3226, PRFECHA@3236, TIPOOP@3239, TIPOOP@3249, TOCUENTA@3252, TOCUENTA@3262, TOTAL@3265, TOTAL@3275, TOTALDECL@3278, TOTALDECL@3288, DECLTERC@3291, DECLTERC@3301, CCAJA@3304, CCAJA@3314, ESTADO@3317, ESTADO@3327, MARCA@3330, MARCA@3340, REGISTRO@3343, REGISTRO@3353, NOTAS@3356, NOTAS@3369

### class fLbi : jServer  (42 métodos, 357 líneas)

init@5141, ListaCampos@5153, NOMBRE@5181, NOMBRE@5191, CUENBIEN@5194, CUENBIEN@5204, CUENDOTA@5207, CUENDOTA@5217, CUENAMORT@5220, CUENAMORT@5230, COSTE@5233, COSTE@5243, RESIDUAL@5246, RESIDUAL@5256, FECHA@5259, FECHA@5269, FBAJA@5272, FBAJA@5282, CBAJA@5285, CBAJA@5295, COEFI@5298, COEFI@5308, PERIODO@5311, PERIODO@5321, MESES@5324, MESES@5334, IVA@5337, IVA@5347, MARCA@5350, MARCA@5360, RECIBIDA@5363, RECIBIDA@5373, PROVEEDOR@5376, PROVEEDOR@5386, REGFECHA@5389, REGFECHA@5399, REGISTRO@5402, REGISTRO@5412, CUADRO@5415, CUADRO@5428, NOTAS@5431, NOTAS@5444

### class fAlbRec : jServer  (38 métodos, 334 líneas)

init@7258, ListaCampos@7278, NUMERO@7304, NUMERO@7314, CNUMERO@7317, CNUMERO@7327, TIPONUM@7330, TIPONUM@7340, CNUMALT@7343, CNUMALT@7353, FECHA@7356, FECHA@7366, PROVEEDOR@7369, PROVEEDOR@7379, FACTURA@7382, FACTURA@7392, PRALBARAN@7395, PRALBARAN@7405, PRFECHA@7408, PRFECHA@7418, IMPORTE@7421, IMPORTE@7431, APUNTES@7434, APUNTES@7444, CPI@7447, CPI@7457, ORDEN@7460, ORDEN@7470, ESTADOREP@7473, ESTADOREP@7483, PEDIDO@7486, PEDIDO@7496, ESTADO@7499, ESTADO@7509, MARCA@7512, MARCA@7522, NOTAS@7525, NOTAS@7538

### class fEmitidas : jServer  (38 métodos, 328 líneas)

init@2734, ListaCampos@2752, NUMERO@2778, NUMERO@2788, CNUMERO@2791, CNUMERO@2801, TIPONUM@2804, TIPONUM@2814, CNUMALT@2817, CNUMALT@2827, FECHA@2830, FECHA@2840, FREGISTRO@2843, FREGISTRO@2853, CLIENTE@2856, CLIENTE@2866, CLCUENTA@2869, CLCUENTA@2879, TIPOOP@2882, TIPOOP@2892, TOCUENTA@2895, TOCUENTA@2905, TOTAL@2908, TOTAL@2918, TOTALDECL@2921, TOTALDECL@2931, DECLTERC@2934, DECLTERC@2944, CCAJA@2947, CCAJA@2957, ESTADO@2960, ESTADO@2970, MARCA@2973, MARCA@2983, REGISTRO@2986, REGISTRO@2996, NOTAS@2999, NOTAS@3012

### class fAlbEmi : jServer  (32 métodos, 285 líneas)

init@6321, ListaCampos@6340, NUMERO@6363, NUMERO@6373, CNUMERO@6376, CNUMERO@6386, TIPONUM@6389, TIPONUM@6399, CNUMALT@6402, CNUMALT@6412, FECHA@6415, FECHA@6425, CLIENTE@6428, CLIENTE@6438, FACTURA@6441, FACTURA@6451, IMPORTE@6454, IMPORTE@6464, APUNTES@6467, APUNTES@6477, CPI@6480, CPI@6490, ORDEN@6493, ORDEN@6503, ESTADOREP@6506, ESTADOREP@6516, ESTADO@6519, ESTADO@6529, MARCA@6532, MARCA@6542, NOTAS@6545, NOTAS@6558

### class fMovBancos : jServer  (30 métodos, 258 líneas)

init@1896, ListaCampos@1908, BANCO@1930, BANCO@1940, NUMERO@1943, NUMERO@1953, CNUMERO@1956, CNUMERO@1966, TIPONUM@1969, TIPONUM@1979, CNUMALT@1982, CNUMALT@1992, TEXTO@1995, TEXTO@2005, AUTOTEXT@2008, AUTOTEXT@2018, CLAVE@2021, CLAVE@2031, FECHA@2034, FECHA@2044, TOTAL@2047, TOTAL@2057, SALDONUE@2060, SALDONUE@2070, ESTADO@2073, ESTADO@2083, MARCA@2086, MARCA@2096, NOTAS@2099, NOTAS@2112

### class fDiario : jServer  (26 métodos, 232 líneas)

init@4474, ListaCampos@4488, ASIENTO@4508, ASIENTO@4518, FECHA@4521, FECHA@4531, TPASIENTO@4534, TPASIENTO@4544, CLAVE@4547, CLAVE@4557, CLAVE_ORI@4560, CLAVE_ORI@4570, TIPO@4573, TIPO@4583, NUMERO@4586, NUMERO@4596, IMPORTE@4599, IMPORTE@4609, CUENTA@4612, CUENTA@4622, SALDO@4625, SALDO@4635, MULTI@4638, MULTI@4648, MARCA@4651, MARCA@4661

### class fExtras : jServer  (26 métodos, 226 líneas)

init@2370, ListaCampos@2382, NUMERO@2402, NUMERO@2412, CNUMERO@2415, CNUMERO@2425, TIPONUM@2428, TIPONUM@2438, CNUMALT@2441, CNUMALT@2451, FECHA@2454, FECHA@2464, TIPO@2467, TIPO@2477, CLAVE@2480, CLAVE@2490, TEXTO@2493, TEXTO@2503, GRUPO@2506, GRUPO@2516, ESTADO@2519, ESTADO@2529, MARCA@2532, MARCA@2542, NOTAS@2545, NOTAS@2558

### class fAlbPre : jServer  (24 métodos, 218 líneas)

init@7773, ListaCampos@7791, NUMERO@7810, NUMERO@7820, CNUMERO@7823, CNUMERO@7833, TIPONUM@7836, TIPONUM@7846, CNUMALT@7849, CNUMALT@7859, FECHA@7862, FECHA@7872, CLIENTE@7875, CLIENTE@7885, IMPORTE@7888, IMPORTE@7898, APUNTES@7901, APUNTES@7911, ESTADO@7914, ESTADO@7924, MARCA@7927, MARCA@7937, NOTAS@7940, NOTAS@7953

### class fAlbPed : jServer  (24 métodos, 218 líneas)

init@8206, ListaCampos@8224, NUMERO@8243, NUMERO@8253, CNUMERO@8256, CNUMERO@8266, TIPONUM@8269, TIPONUM@8279, CNUMALT@8282, CNUMALT@8292, FECHA@8295, FECHA@8305, PROVEEDOR@8308, PROVEEDOR@8318, IMPORTE@8321, IMPORTE@8331, APUNTES@8334, APUNTES@8344, ESTADO@8347, ESTADO@8357, MARCA@8360, MARCA@8370, NOTAS@8373, NOTAS@8386

### class fAlbPedE : jServer  (24 métodos, 218 líneas)

init@9127, ListaCampos@9145, NUMERO@9164, NUMERO@9174, CNUMERO@9177, CNUMERO@9187, TIPONUM@9190, TIPONUM@9200, CNUMALT@9203, CNUMALT@9213, FECHA@9216, FECHA@9226, CLIENTE@9229, CLIENTE@9239, IMPORTE@9242, IMPORTE@9252, APUNTES@9255, APUNTES@9265, ESTADO@9268, ESTADO@9278, MARCA@9281, MARCA@9291, NOTAS@9294, NOTAS@9307

### class fEriva : jServer  (26 métodos, 217 líneas)

init@3657, ListaCampos@3667, TIPO@3687, TIPO@3697, FACTURA@3700, FACTURA@3710, NUMERO@3713, NUMERO@3723, IVA@3726, IVA@3736, IVA_CTA@3739, IVA_CTA@3749, IVA_TOTAL@3752, IVA_TOTAL@3762, RE@3765, RE@3775, RE_CTA@3778, RE_CTA@3788, RE_TOTAL@3791, RE_TOTAL@3801, BASE@3804, BASE@3814, NODEDU@3817, NODEDU@3827, BINVERSION@3830, BINVERSION@3840

### class fInformes : jServer  (26 métodos, 217 líneas)

init@3874, ListaCampos@3885, NUMERO@3905, NUMERO@3914, NOMBRE@3917, NOMBRE@3926, TITULO@3929, TITULO@3938, PGC@3941, PGC@3950, ANCHO_TXT@3953, ANCHO_TXT@3962, SI_MULTI@3965, SI_MULTI@3974, CABECERA@3977, CABECERA@3986, TIPOS@3989, TIPOS@3998, CLAVE@4001, CLAVE@4010, COMPROBAR@4013, COMPROBAR@4025, COLUMNAS@4028, COLUMNAS@4040, PROGRAMA@4043, PROGRAMA@4055

### class fDiarioTxt : jServer  (24 métodos, 204 líneas)

init@4706, ListaCampos@4716, TIPO@4735, TIPO@4745, NUMERO@4748, NUMERO@4758, CUENTA@4761, CUENTA@4771, TEXTO@4774, TEXTO@4784, DOCU@4787, DOCU@4797, MULTI@4800, MULTI@4810, NEGATIVO@4813, NEGATIVO@4823, ACUMULAR@4826, ACUMULAR@4836, ASIENTO@4839, ASIENTO@4849, FECHA@4852, FECHA@4862, NOTAS@4865, NOTAS@4878

### class fVencimientos : jServer  (22 métodos, 197 líneas)

init@1524, ListaCampos@1537, NUMERO@1555, NUMERO@1565, TIPO@1568, TIPO@1578, TPNUMERO@1581, TPNUMERO@1591, FECHA@1594, FECHA@1604, IMPORTE@1607, IMPORTE@1617, PENDIENTE@1620, PENDIENTE@1630, CUENTA@1633, CUENTA@1643, CUENTADEF@1646, CUENTADEF@1656, PENTIDAD@1659, PENTIDAD@1669, PTIPO@1672, PTIPO@1682

### class fRecibos : jServer  (22 métodos, 190 líneas)

init@8596, ListaCampos@8611, TIPO@8629, TIPO@8639, AGENTE@8642, AGENTE@8652, TIPOAP@8655, TIPOAP@8665, DIA@8668, DIA@8678, MES@8681, MES@8691, EJERCICIO@8694, EJERCICIO@8704, IMPORTE@8707, IMPORTE@8717, CONCEPTO@8720, CONCEPTO@8730, RSEPARADO@8733, RSEPARADO@8743, VTO@8746, VTO@8756

### class fIVA : jServer  (22 métodos, 188 líneas)

init@203, ListaCampos@214, TIPO@232, TIPO@242, NUMERO@245, NUMERO@255, TEXTO@258, TEXTO@268, IVA@271, IVA@281, CTA_IVA@284, CTA_IVA@294, IVA_RE@297, IVA_RE@307, CTA_IVA_RE@310, CTA_IVA_RE@320, PORDEFECTO@323, PORDEFECTO@333, INACTIVO@336, INACTIVO@346, ABREVIA@349, ABREVIA@359

### class fAlbInv : jServer  (20 métodos, 181 líneas)

init@7592, ListaCampos@7609, NUMERO@7626, NUMERO@7636, TIPO@7639, TIPO@7649, CNUMERO@7652, CNUMERO@7662, TIPONUM@7665, TIPONUM@7675, CNUMALT@7678, CNUMALT@7688, FECHA@7691, FECHA@7701, APUNTES@7704, APUNTES@7714, MARCA@7717, MARCA@7727, NOTAS@7730, NOTAS@7743

### class fBancos : jServer  (20 métodos, 175 líneas)

init@1721, ListaCampos@1732, NUMERO@1749, NUMERO@1759, NOMBRE@1762, NOMBRE@1772, SUCURSAL@1775, SUCURSAL@1785, NUMCTA@1788, NUMCTA@1798, BIC@1801, BIC@1811, CUENTA@1814, CUENTA@1824, SALDOINI@1827, SALDOINI@1837, SALDOACT@1840, SALDOACT@1850, NOTAS@1853, NOTAS@1866

### class fAlbRep : jServer  (18 métodos, 161 líneas)

init@7994, ListaCampos@8010, TIPO@8026, TIPO@8036, ALBARAN@8039, ALBARAN@8049, FACTURA@8052, FACTURA@8062, IMPORTE@8065, IMPORTE@8075, APUNTES@8078, APUNTES@8088, CPI@8091, CPI@8101, ORDEN@8104, ORDEN@8114, REPARTO@8117, REPARTO@8127

### class fCuentas : jServer  (18 métodos, 156 líneas)

init@391, ListaCampos@402, CUENTA@418, CUENTA@428, TEXTO@431, TEXTO@441, DEBE@444, DEBE@454, HABER@457, HABER@467, PENTIDAD@470, PENTIDAD@480, PDIRECTO@483, PDIRECTO@493, PTIPO@496, PTIPO@506, MARCA@509, MARCA@519

### class fPagos : jServer  (18 métodos, 156 líneas)

init@2154, ListaCampos@2165, BANCO@2181, BANCO@2191, NUMERO@2194, NUMERO@2204, IMPORTE@2207, IMPORTE@2217, VTO@2220, VTO@2230, DIRSUBCTA@2233, DIRSUBCTA@2243, NUMEROT@2246, NUMEROT@2256, BANCOT@2259, BANCOT@2269, DECLTERC@2272, DECLTERC@2282

### class fAjustes : jServer  (18 métodos, 153 líneas)

init@5498, ListaCampos@5508, TIPO@5524, TIPO@5534, NUMERO@5537, NUMERO@5547, CUENTA@5550, CUENTA@5560, IMPORTE@5563, IMPORTE@5573, CONTRA@5576, CONTRA@5586, CAMBIOAS@5589, CAMBIOAS@5599, AFECTAIVA@5602, AFECTAIVA@5612, DECLTERC@5615, DECLTERC@5625

### class fFotos : jServer  (18 métodos, 153 líneas)

init@8786, ListaCampos@8796, TIPO@8812, TIPO@8822, NUMERO@8825, NUMERO@8835, NOMBRE@8838, NOMBRE@8848, MOSTRAR@8851, MOSTRAR@8861, IZQ@8864, IZQ@8874, ARR@8877, ARR@8887, ANCHO@8890, ANCHO@8900, ALTO@8903, ALTO@8913

### class fExApuntes : jServer  (16 métodos, 138 líneas)

init@2596, ListaCampos@2607, NUMERO@2622, NUMERO@2632, EXTRA@2635, EXTRA@2645, CUENTA@2648, CUENTA@2658, AYUDA@2661, AYUDA@2671, DH@2674, DH@2684, IMPORTE@2687, IMPORTE@2697, DECLTERC@2700, DECLTERC@2710

### class fOperaciones : jServer  (14 métodos, 124 líneas)

init@79, ListaCampos@90, TIPO@104, TIPO@114, NUMERO@117, NUMERO@127, TEXTO@130, TEXTO@140, CUENTA@143, CUENTA@153, PORDEFECTO@156, PORDEFECTO@166, IVA@169, IVA@179

### class fFormdoc : jServer  (14 métodos, 123 líneas)

init@4910, ListaCampos@4918, TIPO@4932, TIPO@4942, NUMERO@4945, NUMERO@4955, TEXTO@4958, TEXTO@4968, ENBLANCO@4971, ENBLANCO@4981, COPIAS@4984, COPIAS@4994, DATOS@4997, DATOS@5010

### class fTipoVtos : jServer  (12 métodos, 108 líneas)

init@5033, ListaCampos@5043, NUMERO@5056, NUMERO@5066, TEXTO@5069, TEXTO@5079, CLIDEF@5082, CLIDEF@5092, PROVDEF@5095, PROVDEF@5105, ESTADO@5108, ESTADO@5118

### class fFamilias : jServer  (12 métodos, 105 líneas)

init@6606, ListaCampos@6616, NUMERO@6629, NUMERO@6639, PADRE@6642, PADRE@6652, TEXTO@6655, TEXTO@6665, DCTO@6668, DCTO@6678, TDCTO@6681, TDCTO@6691

### class fAnalitica : jServer  (12 métodos, 103 líneas)

init@9024, ListaCampos@9034, TIPO@9047, TIPO@9057, NUMERO@9060, NUMERO@9070, CUENTA@9073, CUENTA@9083, ACTIVIDAD@9086, ACTIVIDAD@9096, IMPORTE@9099, IMPORTE@9109

### class fFormhoja : jServer  (10 métodos, 93 líneas)

init@5686, ListaCampos@5697, TIPO@5709, TIPO@5719, NUMERO@5722, NUMERO@5732, TEXTO@5735, TEXTO@5745, DATOS@5748, DATOS@5761

### class fFamiliasC : jServer  (10 métodos, 87 líneas)

init@7171, ListaCampos@7181, FAMILIA@7193, FAMILIA@7203, CARNUM@7206, CARNUM@7216, TIPO@7219, TIPO@7229, TEXTO@7232, TEXTO@7242

### class fEtiDat : jServer  (10 métodos, 87 líneas)

init@8509, ListaCampos@8519, TIPO@8531, TIPO@8541, NUMERO@8544, NUMERO@8554, CLAVE@8557, CLAVE@8567, TEXTO@8570, TEXTO@8580

### class fRepForm : jServer  (10 métodos, 86 líneas)

init@9345, ListaCampos@9353, TRABAJO@9365, TRABAJO@9375, NOMBRE@9378, NOMBRE@9388, PORDEFECTO@9391, PORDEFECTO@9401, DATOS@9404, DATOS@9417

### class fEmpresas : jServer  (10 métodos, 85 líneas)

init@3427, ListaCampos@3435, NUMERO@3447, NUMERO@3457, NOMBRE@3460, NOMBRE@3470, MONEDA@3473, MONEDA@3483, HISTORICO@3486, HISTORICO@3496

### class fEtiCod : jServer  (10 métodos, 85 líneas)

init@8424, ListaCampos@8432, TIPO@8444, TIPO@8454, CLAVE@8457, CLAVE@8467, FORMA@8470, FORMA@8480, CODIGO@8483, CODIGO@8493

### class fActividad : jServer  (10 métodos, 85 líneas)

init@8939, ListaCampos@8947, NUMERO@8959, NUMERO@8969, NOMBRE@8972, NOMBRE@8982, ETIQUETA@8985, ETIQUETA@8995, ACTIVA@8998, ACTIVA@9008

### class fReferencias : jServer  (8 métodos, 76 líneas)

init@3, ListaCampos@14, TIPO@25, TIPO@35, NUMERO@38, NUMERO@48, TEXTO@51, TEXTO@61

### class fRefApuntes : jServer  (8 métodos, 76 líneas)

init@3581, ListaCampos@3592, TIPO@3603, TIPO@3613, NUMERO@3616, NUMERO@3626, TPNUMERO@3629, TPNUMERO@3639

### class fArticulosC : jServer  (8 métodos, 73 líneas)

init@7098, ListaCampos@7108, ARTICULO@7119, ARTICULO@7129, CARNUM@7132, CARNUM@7142, DATO@7145, DATO@7155

### class fParametros : jServer  (8 métodos, 72 líneas)

init@547, ListaCampos@555, ETIQUETA@566, ETIQUETA@576, TEXTO@579, TEXTO@589, MAS@592, MAS@602

### class fPargen : jServer  (8 métodos, 69 líneas)

init@3512, ListaCampos@3520, ETIQUETA@3531, ETIQUETA@3541, TEXTO@3544, TEXTO@3554, MAS@3557, MAS@3567

### class fExPlantillas : jServer  (6 métodos, 60 líneas)

init@2310, ListaCampos@2320, TEXTO@2330, TEXTO@2340, CONTENIDO@2343, CONTENIDO@2356

### class fDirectos : jServer  (6 métodos, 51 líneas)

init@8155, ListaCampos@8163, CUENTA@8173, CUENTA@8183, TEXTO@8186, TEXTO@8196

### class fApu  (2 métodos, 32 líneas)

init@5662, init@6711

### class fApuntesPre : fApuntes  (1 métodos, 3 líneas)

init@7991

### funciones/procedimientos sueltos (4)

xCuenta@5651(3), xCuenta12@5654(8), PonGSituacion@5674(6), DameGSituacion@5680(6)

## D_Comun  (37323 líneas)


### class vFormReport : JDDW  (67 métodos, 3436 líneas)

Init@26188, PreFormato@26365, Impresora@26400, Arriba@26410, Abajo@26442, MasTodos@26474, Mas@26499, Menos@26531, MenosTodos@26555, Setup2@26600, SetupGrid@26685, columna@26730, GridPonValor@26779, ListViewMouseButtonDoubleClick@26809, ActualizarLV@26816, Refresca@26842, PonAnchoTotal@26856, PonNombreImpresora@26908, GridDobleClick@26941, EditFocusChange@26945, Otros@26958, LeePreFormatos@27028, PonPreFormato@27067, Tools@27504, LeeFormatos@27530, Formatos@27559, FormatosMenu@27613, FormatosLeer@27668, FormatosCrear@27762, FormatosPorDefecto@27790, FormatosNombre@27821, FormatosBorrar@27844, FormatosGrabar@27918, FormatosModificar@27983, ExportarMenu@27991, CreaFichero@28036, CompruebaDCON@28278, ExportarDBF@28307, ExportarDBFTotales@28414, CalculaPaginas1@28460, CalculaPaginas2@28483, FMVariable@28514, GridBuscar@28559, FMApunte@28662, noMismoNivel@28821, RecolocaSegunNivel@28836, TipoPreformato@28928, ButtonClick@29038, ImprimirTotales@29056, AbreRepForm@29329, CalculaPaginas@29350, FMApunteTotales@29383, ImprimirDiferido@29406, imp_HojaDiferida@29716, cTituloTrabajo@29825, cTituloGeneral@29828, cTituloGeneral@29831, cTituloTrabajo@29834, cTituloFichero@29838, MiraDriver@29847, PostInit@29912, ImpresoraPDF@29924, Calculados@29946, ValorColumna@30283, ValorFormula@30292, MiraTiposLetra@30524, ExportarExt@30565

### class FormatoHoja  (42 métodos, 2171 líneas)

CadFuenteNC@16262, CadAlineacion@16265, EditaLineas@16305, CadLinea@16347, init@16354, DimeArray@16374, GrabaNumero@16400, Graba@16469, EsVariable@16555, NumRegistros@16573, CambiosRegistro@16576, aFuente@16728, ReleeCadFuentes@16751, CadFuente@16765, CambioFuentes@16772, Lee@16846, GraficoMueve@16965, MuestraOrden@16986, ImprimeV@16997, oFuente@17034, ImprimeOrdenesV@17060, MuestraColor@17474, EditaTextos@17568, GenerarCuadroSimpleBase@17650, GenerarCuadroSimpleSS@17653, GenerarCuadroX@17780, ImprimeGuardaApuntes@18059, ImprimeRecuperaApuntes@18069, ImprimeMasLinea@18081, ImprimeVDif@18116, EditaApuntes@18170, PONacApuntesVariables@18224, GenerarCuadro@18237, EditaVariables@18262, GenerarCuadroSimpleSC@18303, GenerarCuadroSimple@18365, GenerarCuadroCGris@18372, GenerarCuadroPijama@18496, BorraUno@19895, PonUnFM@19951, ImprimeOrdenesTest@22650, PonFirma@22986

### class vModeloV : vVisor  (57 métodos, 1998 líneas)

Muestra@19349, MouseDrag@19376, DragInicio@19445, EdAlinear@19629, RehazSegunXY@19682, PulsadoDelete@19865, HistoricoPush@19907, DragMuestra@19929, HistoricoPop@19998, Edita@20019, Refresh@20103, MiraZona@20146, MarcaOrden@20158, Pix2Columna@20179, Pix2Fila@20182, Zoom@20186, x2Pix@20193, MouseButtonDoubleClick@20213, DragMarcaTodos@20225, BotonDerecho@20274, Remuestra@20280, y2Pix@20294, MouseButtonDown@20311, Activa@20340, BotonIzquierdo@20448, DameMarcados@20501, Destroy@20518, MouseMove@20525, MuestraMarcados@20550, Marcar@20662, PonZona@20845, PonCursor@20886, DameApuntados@20913, Mouse2X@20963, Mouse2Y@20966, EdMismoTam@20970, MuestraDato@21002, Init@21017, EdCentrar@21059, EditaPrincipal@21125, EdSeparaciones@21136, EdAsignarFuente@21199, Deshacer@21449, BloqueMarcados@21478, DragFinal@21666, BorraApLinTxt@21799, EdAsignarAlineacion@21828, ActualizarToolbar@22050, TeclaPulsada@22165, DragMoverBloque@22264, DeshacerNuevos@22362, EdAsignarNegrita@22392, LeeOrdenesRefresh@22416, EligeApuntado@22446, MuestraPreformato@22498, MouseButtonUp@22861, PonFirma@22975

### class vModelo : DIALOGWINDOW  (30 métodos, 1348 líneas)

Init@19197, Destroy@19211, Imprimir@19219, MenuAjustar@19261, MenuCommand@19278, Resize@19333, BDEjecuta@19485, LeeOrdenes@20265, BotonDerecho@20697, GeneraLista@21226, Configura@21525, Seleccionar@21714, SeleccionarTodos@21764, DeSeleccionar@21855, Copiar@21882, Pegar@21906, Cortar@22041, SeleccionarUnFondo@22075, Terminar@22119, Close@22137, ControlErrores@22149, expose@22243, BDaCero@22315, Nuevo@22332, Preformato@22477, Setup@22568, MouseButtonUp@22869, MouseButtonDown@22877, Dispatch@22884, OrdenarApuntes@22897

### class clFormatos  (34 métodos, 1247 líneas)

LeeDocs@14284, MenuEjecuta@14333, PorDefectoGraba@14358, PorDefectoImprime@14397, PosicionParam@14417, PorDefectoPosicion@14485, PosicionHojas@14520, Borra@14573, EligeTipo@14606, PosicionTipo@14623, ownerFM@14643, cTipo@14646, acMasVariables@14649, Reparte@14670, cTipo@14812, MiraDocs@14816, PosicionDato@14823, PosicionVistaPrevia@14833, PosicionConfImpresora@14860, PosicionDriver@14891, CopiaHojas@14933, MenuLanza@14996, MenuEdita@15098, MenuEdNuevo@15147, MenuEdCopiaDe@15150, MenuEdModificar@15170, MenuEdBorrar@15177, MenuEditaUno@15182, PonGSituacion@15198, init@15236, aDocs@15254, Graba@15262, imprimeV@15313, MenuEjecutaNumImpresion@15493

### class rParGen : BaseParametros  (19 métodos, 1097 líneas)

Leer@8392, Grabar@8633, AdvierteVtosPagados@9694, AdvierteBancosEnExtras@9712, init@10369, LeerOtrasAplicaciones@10472, GrabarOtrasAplicaciones@10497, LeerDeclTerceros@10573, GrabarDeclTerceros@10591, LeerFondo@10632, AdvierteStockNegativo@10684, LeerDiasIVA@11017, GrabaUsuarios@11665, LeeUsuarios@11702, LeerMarcasTipo@11807, GrabarMarcas@11832, LeerMarcas@11855, AdvierteFechaFacturas@12314, AdvierteIVAenExtrasBancos@12336

### class clPGC  (34 métodos, 1069 líneas)

init@6585, _CreaBloque@6590, _DameBloque@6600, EligeUno@6612, RotuloSinPlan@6650, Titulo@6654, CCambiaUnDBF@6712, CCambiaContactos@6715, CCambiaCuentas@6752, _CCambiaUna@6800, CGeneraGrupos@6819, MiraPGC@6830, _LeePGC@6861, General@6875, V@6881, ConversionCuentas@6891, _ConvierteCuentas@6947, CambiaPlan@6993, CCambiaUnDBFtxt@7048, _ListaCuentas@7069, ConversionDBF@7122, _ClavesValores@7304, EligeUnoConversion@7315, _LeeFichero@7706, _LeeParGen@7952, CCambiaPlCierre@7993, EligeUnoMenu@8023, aLeeLista@8051, _ListaEquivalencias@8072, _LeeCuentas@8097, CCambiaDBFs@8129, Informe@8185, CCambiaUnDBFdb@8242, CGeneraGruposTMP@8266

### class vEmpresas : jDLVRed  (20 métodos, 998 líneas)

Busca@3944, ImpNuevoRegistro@3967, Edita@3983, Borra@4059, LeeNombre@4074, Imprime@4082, Otros@4095, Ordenar@4210, Recuperar@4283, BorradoDefinitivo@4395, columna@4653, LeeParametros@4675, CambioNumero@4717, ListaEmpresas@4784, CreaEmpresaPruebas@5047, ImpFuncion@5368, siAdministradorUnico@5485, GridPonValor@5494, CambioHistorico@5502, EditaNueva@5690

### class rParametros : BaseParametros  (31 métodos, 910 líneas)

Grabar@1326, Leer@1520, init@1813, GrabarNumeraciones@1820, LeerNumeraciones@1833, LeerNum0@1859, LeerNum1@1883, GrabarNum0@1899, plEmitidas@1933, plRecibidas@1937, plExtras@1940, plAlbEmitidas@1943, plAlbRecibidas@1946, plAlbPresupuestos@1949, plAlbInventarios@1952, plantilla@1955, tipoNumDefecto@1969, plCompleta@2002, plMenuYopciones@2082, plGrabaDB@2175, plNumSegunDBF@2212, DameNums@2239, plAlbPedidos@2251, DamePlantillas@2254, plAlbPedidosE@2499, LeerAlmacenes@2507, GrabarAlmacenes@2521, plMovBan@2536, GrabarPeriodosContables@2589, LeePeriodosContables@2646, DameNumPeriodoContable@2668

### class vGenCuadro : JDDW  (8 métodos, 760 líneas)

_GrabaDatos@36211, GridPonValor@36266, Init@36275, LATodasIgual@36477, LCTodasIgual@36497, Setup2@36989, PreparaGrid@37050, PostInit@37164

### class xFusion  (15 métodos, 717 líneas)

NotepadClaves@23567, LeeOpciones@23719, AbrirDocumento@23737, ProcesoInicio@23799, Graba@23955, ProcesoFinal@23975, CreaFichero@24014, Cierra@24018, GrabaComunes@24022, Lanza@24141, init@25542, LanzaW@25549, GeneraFPT@25643, LanzaDirecto@25693, Ejecuta@25737

### class clRed  (25 métodos, 676 líneas)

Abrir@31133, Bloquear@31223, Bloquear_SiUnico@31294, BloquearControl@31302, Cerrar@31321, DesBloquear@31354, DesbloquearControl@31389, NO@31405, siCambios@31455, init@31497, SiExclusivo@31507, SiAdministrador@31511, SiExclusivoTotal@31515, elUnico@31534, SiExclusivoEmpresa@31569, PonRutina@31578, LogAbrir@31591, LogCerrar@31615, PonEmpresa@31626, MostrarEstado@31654, LogGrabar@31704, PonteExclusivoTotal@31774, ComprobarDB@31790, CreaDB@31835, MiraDosVeces@31845

### class vCambioPGC : JDDW  (17 métodos, 638 líneas)

Init@7177, Recalculo@7259, PostInit@7298, Setup2@7353, PonGridCuentas@7375, LeeDatos@7393, dbMinimos@7417, GridPonValor@7458, _GrabaDatos@7470, PonGridEquivalencias@7508, LeeEquivalencias@7525, LeeEmpresas@7566, EscribeLCSE@7620, CuentasSinEquivalencia@7632, ListBoxSelect@7700, Informe@7782, LeeCuentas@8115

### class vVisorDlgX : vVisorDlg  (10 métodos, 617 líneas)

ListaElegidos@24072, PDFCreaFichero@24087, PDFCorreo@24115, PDFCreaFicheroOrdenes@24162, PDFCrear@24420, PDFPosicionFDySetup@24822, PDFFirmaDigital@25321, PDFFirmaDigitalRecuadro@25443, PDFCrearRapido@25639, PDFCorreoOutlook@25713

### class vParGenVideo : DATAWINDOW  (24 métodos, 613 líneas)

Init@9420, CTexto@9869, CFondo@9876, CTextoElegido@9885, CFondoElegido@9892, CFondoGeneral@9900, PonerColorTexto@9936, Leer@9944, Grabar@9959, PorDefecto@10024, PonerColorBackground@10031, Muestra@10051, PonerColor@10080, PonerFont@10087, CTipoLetra@10104, MuestraTipoLetra@10116, CTextoCabecera@10139, CFondoCabecera@10146, CRecuadro@10154, ButtonClick@10167, PonerBoton@10177, CFondoPunteados@10619, CTextoNumerosNegativos@10675, PostInit@12289

### class vImporta : JDDW  (21 métodos, 586 líneas)

Init@5802, base@5865, Empresa@5871, Nada@5884, _GrabaDatos@5896, EscribeLV@5975, LeeRegistros@5996, MiraCuenta@6167, GrabaInforme@6194, Todo@6228, modelos@6243, GrabaIVA@6249, GrabaOperaciones@6267, GrabaPlantillas@6284, GrabaFormHoja@6311, GrabaCuentas@6323, ModBase@6339, ModComun@6342, Setup2@6352, GrabaReferencias@6378, PostInit@6391

### class clBandas  (9 métodos, 521 líneas)

LeeBandasUsadas@32397, RotuloBandasUsadas@32895, Elige@32912, Elige1@32974, RotuloBanda@33014, dameBanda@33021, ContenidoBanda@33050, LeeBandas@33073, LeeBandasTipo@33099

### class BaseApuntesER  (17 métodos, 519 líneas)

Agregar@12595, CambioCuenta@12599, Contabilidad@12604, Cuenta@12624, Init@12631, NumApuntes@12644, NumAsientos@12647, SumaAfectaIVA@12674, SumaTipo@12686, IRPF@12699, IRPFBuscaCuenta@12765, Lee@12789, Graba@12813, Exporta@12849, IRPFImporte@12866, SumaDeclTerceros@12881, Borra@12894

### class vParGenRed : DATAWINDOW  (17 métodos, 500 líneas)

Init@11259, Leer@11334, Menos@11399, Grabar@11413, columna@11430, Mas@11505, Copiar@11533, eligeBandas@11551, eligeClave@11559, GridPonValor@11574, PostInit@12283, ALT9adm@12356, ponALT9@12363, eligeALT9@12377, ponDatosServidor@12387, DatosServidor@12394, eligeEmpresas@12532

### class BaseServidores  (30 métodos, 493 líneas)

Init@3451, Abrir@3461, Cerrar@3494, QueFichero@3505, MarcaPosiciones@3508, RecuperaPosiciones@3524, Registrar@3566, TitFichero@3576, CompruebaFDTodos@3579, ReordenaTodos@3620, NumDBFs@3672, SiAbierto@3676, SuspendNotification@3685, ResetNotification@3698, ListaMalCerrados@3712, BorraMalCerrados@3731, HayMalCerrados@3743, N@3750, DBFCierra@3764, SoloLectura@3773, Zap@3776, X@3780, Unlock@3795, siSeHaGrabado@3815, l64@3829, l64ext@3845, Lock@3867, NomFichero@3884, MarcaPosicionesExt@3888, RecuperaPosicionesExt@3901

### class clOpBandas  (15 métodos, 484 líneas)

CambioBanda@32426, Coloca@32447, ColocaBandaPrincipal@32465, ColocaSubTB@32496, ColocaTB@32535, Contenido2Lista@32567, Editar@32624, Eliminar@32695, LeeBandas@32708, LeeOpciones@32715, Lista2Contenido@32744, Menu@32772, MenuEjecuta@32828, init@32886, Contenido2ListaID@33058

### class vEFormatoDoc : JDDW  (20 métodos, 481 líneas)

Init@15578, Mas@15676, Menos@15686, Arriba@15699, Abajo@15713, CambiaCondicion@15729, EscribeLV@15744, _GrabaDatos@15777, ControlErrores@15786, DameNumero@15807, DameMemoLista@15814, _DBF2Variables@15855, ListViewMouseButtonDoubleClick@15893, EditaHojaActual@15912, PonNombreImpresora@15948, Impresora@15981, EscondeControles@16004, CambiaCuantasVeces@16049, PostInit@16244, ImpresoraPDF@16250

### class vFVariables : JDDW  (13 métodos, 449 líneas)

_GrabaDatos@35840, BorraColor@35858, CambiaColor@35861, ControlErrores@35864, Habilita@35900, Init@35919, PBEmpresa@36085, PBGenerales@36088, PBVariables@36092, TipoLetraMas@36096, Setup2@36922, PostInit@37158, Modificador@37175

### class vParGenFacturas : DATAWINDOW  (16 métodos, 444 líneas)

Init@10253, Defecto@10362, Leer@10557, GridPonValor@10607, DeclTerceros@10657, DiasIVA@11048, LeerDeclTerceros@11075, LeerDiasIVA@11108, ButtonClick@11162, PonDiasIVA@11172, CFondoPagar@12173, CFondoCobrar@12178, CFondoPagarQuitar@12199, CFondoCobrarMenos@12204, PonerColorBackground@12209, PostInit@12265

### class clInfoAdicional  (13 métodos, 423 líneas)

LeeDatos@13171, LeeEtiquetas@13218, Graba@13244, init@13381, PonEtiquetasDLV@13429, LeeDLV@13440, GrabaDLV@13653, LeeCampo@13705, FMVariable@13739, FMListaVariables@13770, EtiquetasFiltro@13814, BuscaEtiqueta@14221, BuscaEtiquetaNum@14242

### class vFTextos : JDDW  (11 métodos, 382 líneas)

_GrabaDatos@35469, BorraColor@35493, CambiaColor@35496, ControlErrores@35499, Init@35524, MultiLinea@35665, PonTexto@35686, Setup2@35709, TipoLetraMas@35744, PostInit@37152, Modificador@37180

### class vPreFormato : JDDW  (13 métodos, 363 líneas)

Init@27158, Setup2@27260, EscribeLV@27310, ListViewMouseButtonDoubleClick@27347, EscribeLVReg@27374, EdTipoLetra@27386, EdNegrita@27413, EdCursiva@27430, EdColor@27448, ControlErrores@27477, _GrabaDatos@27488, ListBoxSelect@29858, PostInit@29918

### class vFormatosHoja : jDLVRed  (11 métodos, 360 líneas)

Edita@34263, Setup2@34272, CopiaHoja@34279, CopiaHojaOtra@34314, MasHojas@34383, NumeroNueva@34405, Busca@34432, Borra@34459, Otros@34476, EditaNueva@34538, Limpia@34549

### class clModificador  (10 métodos, 346 líneas)

cTexto@18695, init@18698, Lee@18707, LeeAntiguo@18716, Etiqueta@18809, Procesa@18829, ProcesaUno@18844, Edita@18981, EtiquetaBoton@19022, Muestra@19031

### class jRepForm  (7 métodos, 341 líneas)

init@25838, Imprimir@25849, FR_Columnas@25870, ImpNuevoRegistro@25968, ImpFuncion@25984, TipoPreformato@26015, Nivel@26028

### class vPDFFirma : DATAWINDOW  (11 métodos, 335 líneas)

Init@24638, ConfTarjeta@24963, GuardarCertificado@24991, GuardarMotivo@25005, GuardarContacto@25014, GuardarUbicacion@25022, GuardarRecuadro@25031, PonTipoCertificado@25169, BuscarPFX@25197, ListBoxSelect@25498, PostInit@25526

### class vFGraficos : JDDW  (10 métodos, 335 líneas)

_GrabaDatos@34909, Borrar@34919, Buscar@34937, ControlErrores@34947, Init@34996, MiraFicheros@35082, Setup2@35106, AjustaAlto@37081, AjustaAncho@37103, PostInit@37140

### class vBandas : DATADIALOG  (14 métodos, 332 líneas)

Init@31988, Menos@32045, arriba@32065, abajo@32082, Setup@32099, columna@32151, GridPonValor@32165, GridTomaValor@32181, aceptar@32184, cancelar@32206, MenuCommand@32213, ponToolbar@32241, CambiaIcono@32375, PostInit@32968

### class vPDF : JDDW  (7 métodos, 327 líneas)

Init@24391, Setup2@24853, PorDefectoInicial@25052, PorDefectoParam@25077, ControlErrores@25215, _GrabaDatos@25261, PostInit@25508

### class vCalculados : JDDW  (10 métodos, 313 líneas)

Init@30065, _GrabaDatos@30129, ControlErrores@30168, LanzaMenu@30181, Setup2@30202, Tools@30396, PonOpcionesMenu@30410, ListBoxSelect@30448, ButtonClick@30491, MiraTipo@30499

### class CSV  (16 métodos, 307 líneas)

init@866, columna@874, Pregunta@893, LeeFichero@918, LanzaPython@968, valor@1061, cerrar@1078, leeRegistro@1090, ponteInicio@1118, siClave@1122, valorDecimal@1128, mensImportando@1132, EligeFichero@1138, comoClave@1158, linea@1165, EoF@1169

### class vFApuntes : JDDW  (9 métodos, 305 líneas)

_GrabaDatos@34664, BorraColor@34684, CambiaColor@34687, ControlErrores@34691, Init@34713, TipoLetraMas@34858, Setup2@36873, PostInit@37134, Modificador@37170

### class vEInfoAdicional : DATAWINDOW  (19 métodos, 301 líneas)

Init@13484, ActivaGrid@13548, Graba@13551, GridPonValor@13557, GridSiEditamos@13564, Setup@13572, FMListaVariables@13752, FMVariable@13755, Nuevo@13844, Visualizar@13855, Borrar@13864, MuestraLV@13876, ListViewMouseButtonDoubleClick@13904, Borrar1@13911, Nuevo1@13914, Visualizar1@13917, PostInit@14157, CopiaOtro@14176, PonValor@14231

### class vFLineas : JDDW  (7 métodos, 290 líneas)

_GrabaDatos@35185, BorraColor@35198, CambiaColor@35201, ControlErrores@35204, Init@35248, Setup2@35366, PostInit@37146

### class vParGen : JDDW  (4 métodos, 286 líneas)

Init@8803, PostInit@8832, _GrabaDatos@8951, ControlErrores@9254

### class vOrdenar : JDDW  (10 métodos, 279 líneas)

Init@3172, Cabeceras@3217, NuevoRegistro@3223, PostInit@3230, Primero@3239, Anterior@3268, Siguiente@3295, Ultimo@3322, _GrabaDatos@3351, columna@3366

### class clAccess  (6 métodos, 253 líneas)

Trabaja@33977, FicheroMDB@34006, GeneraDAT@34038, CreaMDB@34080, init@34126, GeneraUno@34130

### class RecrearInternos  (5 métodos, 247 líneas)

Final@2782, Dependiente@2787, Procesa@2815, Init@3002, DependienteMenos@3009

### class vParGenBase : DATAWINDOW  (4 métodos, 241 líneas)

Init@9143, Defecto@9300, GridSiEditamos@10653, PostInit@12247

### class clJustificantes  (6 métodos, 237 líneas)

LeeDatos@13927, Graba@13959, MenuLanza@14025, MenuEjecuta@14058, Nuevo@14085, init@14214

### class clUsuario  (10 métodos, 224 líneas)

lee@31009, texto@31042, textoL@31066, textoC@31069, textoA@31073, textoN@31086, leeA@31092, PonAdministrador@31870, siALT9@31914, AccesoLimitadoEmpresas@31931

### class vParGenEtiMar : DATAWINDOW  (6 métodos, 210 líneas)

Init@11969, ButtonClick@12055, Marca@12069, Etiqueta@12136, EtiCliProv@12151, PostInit@12259

### class BaseFusion  (10 métodos, 195 líneas)

LeeCabeceras@23147, init@23172, Error@23206, final@23211, BuscarClave@23216, InteractivasLee@23262, Abrir@23277, Cerrar@23292, InteractivasTipo@23301, InteractivasMira@23327

### class vPDFBase : DATAWINDOW  (6 métodos, 188 líneas)

Init@24275, BuscarPDF@24916, GuardarAutor@24944, GuardarSiFirma@24956, GuardarSiCorreo@25479, PostInit@25520

### class vPGC : DIALOGWINDOW  (8 métodos, 182 líneas)

Buscar@6397, Init@6470, Setup@6516, Terminar@6539, Close@6542, MenuCommand@6546, BuscaUna@6555, PostInit@6568

### class vNEmpresas : JDDWumSLE  (8 métodos, 181 líneas)

Init@4478, PonTextoNumero@4519, EditFocusChange@4541, _GrabaDatos@4549, ControlErrores@4552, Setup2@4575, Escape@4634, PostInit@5661

### class BaseParametros  (13 métodos, 176 líneas)

Etiquetas@1461, TodasEtiquetas@1480, LeerEtiqueta@1489, LeerClaveEtiqueta@1496, BuscarClaveEtiqueta@1503, LeerComandos@1706, GrabarComandos@1751, ValorComando@1792, EscribirComando@1797, init@1808, EscribirComandoL@2280, ValorComandoS@2430, ValorComandoN@2504

### class vParGenMas : DATAWINDOW  (3 métodos, 167 líneas)

Init@10780, Defecto@10991, PostInit@12271

### class jMenu : MENU  (8 métodos, 161 líneas)

init@33408, MasMenu@33417, DameTB@33431, MasTB@33466, MasTBsep@33484, MasOpcion@33522, Opcion@33536, datosID@33552

### class fusionTxtRtf : BaseFusion  (6 métodos, 153 líneas)

ConvertirClave@23401, DeterminaTipo@23413, ConvertirClaveRTF@23425, ConvertirClaveTxt@23438, Fusionar@23452, ConvertirClaveHTM@23524

### class vForm : jDLVRed  (7 métodos, 137 líneas)

ActualizaDB@16107, Borra@16131, CopiaActual@16143, Edita@16179, EditaNuevo@16196, EditaUno@16209, Otros@16225

### class vParGenIdioma : DATAWINDOW  (4 métodos, 124 líneas)

Init@12408, Grabar@12441, GridPonValor@12472, Leer@12490

### class vInteractiva : DATADIALOG  (5 métodos, 124 líneas)

Init@23033, Setup@23088, aceptar@23107, cancelar@23121, PostInit@25532

### class clColReport : clFM  (7 métodos, 121 líneas)

Lee@27901, CadAlineacion@28392, MiraDecimales@28408, esSumable@28792, LeeFormula@30458, EscribeFormula@30476, Escribe@30545

### class vParGenOtras : DATAWINDOW  (6 métodos, 110 líneas)

Init@10409, Leer@10440, Grabar@10510, GridComando@10531, GridPonValor@10544, Menos@10549

### class vParGenAdvierte : DATAWINDOW  (3 métodos, 101 líneas)

Defecto@9602, Init@9640, PostInit@12238

### class vParGenCS : DATAWINDOW  (2 métodos, 101 líneas)

Init@9774, PostInit@12253

### class Servidores : BaseServidores  (3 métodos, 91 líneas)

Init@2691, RegistrarDBFs@2709, ReordenaTodos@2760

### class vDesdeHasta : JDDWumSLE  (9 métodos, 87 líneas)

Init@61, desde@99, desde@102, hasta@105, hasta@108, _GrabaDatos@116, ControlErrores@120, Escape@393, PostInit@779

### class vBandasImg : DATADIALOG  (3 métodos, 83 líneas)

Init@32292, Setup@32310, MenuCommand@32350

### class vParGenMoneda : DATAWINDOW  (2 métodos, 82 líneas)

Init@10915, PostInit@12277

### class clFM  (12 métodos, 79 líneas)

NumFLOAT@17378, NumINT@17385, NumDWORD@17392, Escribe@17399, PonDato@17402, Cadena@17406, NumINT1@17554, Logico@17766, Simbolo@17773, LeeModificador@18797, cModificador@18801, Lee@19082

### class vEMPRESAS  (1 métodos, 78 líneas)

FR_@5372

### class clFMApunte : clFM  (4 métodos, 78 líneas)

LeeApunte@17347, Escribe@17477, LeeCampo@18150, init@18488

### class clFMPreFormato : clFM  (3 métodos, 78 líneas)

Lee@17688, init@17717, Escribe@17741

### class clMarcaEx  (3 métodos, 62 líneas)

init@33915, Rellena@33930, Graba@33973

### class jDLVRed : jDLV  (3 métodos, 61 líneas)

MiraRed@30958, ConsultaRed@31644, ConsultaALT9@31903

### class DeclTerceros  (4 métodos, 57 líneas)

init@13114, CBPonValor@13132, CBPonDefecto@13155, CBLeeValor@13161

### class clGenCuadro  (1 métodos, 52 líneas)

init@18313

### class ListaOrdenada  (10 métodos, 51 líneas)

Axit@621, cerrar@628, dbf@632, elementos@636, init@639, nuevo@652, suma@659, Valor@662, zap@666, busca@669

### class clFMVariable : clFM  (3 métodos, 46 líneas)

Lee@17455, Escribe@17534, init@18481

### class clFMTexto : clFM  (3 métodos, 45 líneas)

Lee@17436, Escribe@17515, init@18474

### class vEtiquetas : jDLV  (4 métodos, 39 líneas)

Columna@33569, GridPreguntaColor@33577, Otros@33583, CambiaColor@33674

### class clFusionFichero  (2 métodos, 35 líneas)

init@23379, reAbrir@24059

### class HojaColor  (3 métodos, 28 líneas)

init@19086, PonColor@19092, CambiaColor@19111

### class fFusion : jServer  (7 métodos, 28 líneas)

init@23351, CLASE@23354, NOMBRE@23357, TIPO@23360, NUMERO@23363, DECIMALES@23366, TEXTO@23369

### class clFMLinea : clFM  (2 métodos, 24 líneas)

Lee@17423, Escribe@17504

### class FEImportes : FIELDSPEC  (1 métodos, 22 líneas)

Init@30869

### class FEImportesVar : FIELDSPEC  (1 métodos, 20 líneas)

Init@30891

### class clformatos  (1 métodos, 18 líneas)

acApuntes@14652

### class clFMGrafico : clFM  (2 métodos, 18 líneas)

Lee@17413, Escribe@17496

### class FECadenaVar : FIELDSPEC  (1 métodos, 12 líneas)

Init@30939

### class FSCuentaX : FIELDSPEC  (1 métodos, 11 líneas)

Init@30928

### class jDDW  (2 métodos, 11 líneas)

ConsultaRed@31649, ConsultaALT9@31908

### class FSInteractiva : FIELDSPEC  (1 métodos, 9 líneas)

init@23342

### class FSCuenta : FIELDSPEC  (1 métodos, 9 líneas)

Init@30919

### class FSClave : FIELDSPEC  (1 métodos, 8 líneas)

Init@30911

### class JDDW  (2 métodos, 7 líneas)

Desbloquea@30951, Bloquea@30954

### class JDDL  (2 métodos, 7 líneas)

Bloquea@31896, Desbloquea@31900

### class BMPRecibidas : Bitmap  (1 métodos, 6 líneas)

Init@14257

### class BMPEmitidas : Bitmap  (1 métodos, 6 líneas)

Init@14263

### class BMPExtras : Bitmap  (1 métodos, 6 líneas)

Init@14269

### class BMPProveedores : Bitmap  (1 métodos, 6 líneas)

Init@14275

### class BMPClientes : Bitmap  (1 métodos, 3 líneas)

Init@14281

### funciones/procedimientos sueltos (130)

PNumero@17(44), ReduceMemo@132(24), SNumero@156(9), LeeImporte@165(12), TNumero@177(4), NuevoNumero@181(49), LeeBanco@230(19), eMailMGD@249(12), MovimientoPeligroso@261(43), FiltraDesdeHasta@304(3), cFiltroDesdeHasta@307(3), MarcaDesdeHasta@310(29), urlMGD@339(12), NtrimPunto@351(6), dPNumero@357(20), ValComa@377(16), ControlFechaContable@403(25), NoSoloLectura@428(7), siEntreDesdeHasta@435(3), LeeNumero@438(15), CorrigeFD@453(25), NuevoCNumero@478(29), UltimaCopiaSeguridad@507(31), PNumero0@538(4), LeeDesdeHasta@542(14), DBFTemporal@556(4), FichTemporal@560(18), NuevoNumeroTipo@578(43), NuevoCNumeroDef@672(15), ClaveSegunDBF@687(47), ValImportes@734(31), ValEntero@765(14), cPideFicheroDIR@785(23), NombreBanco@808(22), dirEmpresa@830(3), nEligeGlobal@833(8), PonVersionDir@841(25), aValor2Array@1173(153), PonEtiIVA@1689(17), plantAlb@2284(11), plantEmi@2295(11), plantExtra@2306(10), plantillaAlb@2316(37), plantillaCon@2353(26), plantillaExtra@2379(10), plantillaFact@2389(30), plantRec@2419(11), FCuenta@2433(34), FCuentaAlReves@2467(32), IniGSPlantillas@2539(29), plantMovBan@2568(10), plantillaMovBan@2578(11), RecreoDeInternos@2859(143), EdicionEmpresas@4001(58), CreaNuevaEmpresa@4133(77), VaciaFacturacion@4808(157), VaciaEmpresa@4965(82), privatiza@5345(3), privServer@5348(7), privatizaN@5355(13), ListaEmpresas@5450(13), DameEmpresa@5463(22), EligeEmpresa@5515(73), EligeEmpresaMulti@5588(73), CompruebaEmpresaBase@5667(23), ImportaTipos@6185(9), AyudaPGC@6510(6), CambioPGC@6674(38), MiraPGC@6823(7), PGCempresa@7093(29), AdaptacionPGC@7272(26), EditaParGen@9055(88), ERContras@9288(12), LeeCuenta@12568(27), siInfoAdicional@13627(26), cTipoInfoAdicional@13675(30), BorraInfoAdicional@13714(25), FRInfoAdicional@13781(33), siTieneJustificantes@14165(11), clApuFormAdd@15207(11), FMVarNota@15218(18), DameNumeroForm@16023(26), EdicionFormatos@16067(40), EditaGraficos@16268(37), FMLeeVariableID@16590(36), FMSiEsVariableID@16626(5), FMVariablesID@16631(23), FMTituloVariableID@16654(9), FMTituloVariableX@16663(10), FMVariablesX@16673(18), FMValorX@16691(37), listaModificadores@18952(29), aFormasGraficas@19114(10), aHojaOrden@19124(73), Pix2rpvL@20421(27), MultiLinea@21029(30), WriteText@21333(116), FusionarTXTRTFHTM@23511(13), CreaPDFRapido@25575(64), jFormCreaDBF@26019(9), jFormReportDBF@26576(24), jFormReport@28597(65), PreFormatoAuto@28881(47), GrabaDCON@28940(7), LeeDCON@28947(91), DestinoExtensiones@29869(43), pyExtensiones@30698(63), FR_aDLV@30761(108), SiPermisos@31409(46), IniRed@31785(5), EdicionEtiquetas@33599(75), Marca_aDLV@33683(24), Marca_PonColor@33707(18), Marca_Graba@33725(16), Marca_Columna@33741(19), EtiFormatos@33760(40), Marca_FR@33800(16), siTieneMarca@33816(17), Marca_ImpFuncion@33833(14), Marca_SubMenu@33847(3), Marca_Otros@33850(65), EdicionFormatosHoja@34230(33), Edita1Hoja@34497(41), TipoLetraMas@37185(20), ALT9@37205(42), AsignaCarpetaServidor@37247(14), ficheroDatosServidor@37261(6), compruebaCarpetaDatos@37267(33), guardaNuevaActualizacion@37300(6), dameCarpetaServidor@37306(18)

## E_Edicion  (54123 líneas)


### class clFiltro  (125 métodos, 4825 líneas)

PonRegistros@33507, Anular@33528, Comando@33545, FImporte@33896, XPendienteUnExtra@33917, XPendienteUno@33932, LanzaMenuDirecto@33955, EjecutarDirecto@33973, Cerrar@34029, Guardar@34064, Orden@34141, IniciaDirecto@34164, LanzaMenu@34231, EjecutarFiltro@34283, SegunDBFClave@34318, SegunDBFTipo@34322, GrabaFiltros@34340, LeeFiltros@34364, siTrabajando@34416, Ejecutar@34419, SegunDBFMenu@34447, nFiltros@34798, BorrarFiltro@34810, SegunDBFColocate@34840, Reiniciar@34977, OrdenarFiltros@35035, FNumeracionNumero@35070, FClienteProveedor@35086, FCuentasDiario@35122, FTipoCuenta@35136, FTiposClPr@35150, FContieneTexto@35174, FDeclTerceros@35197, FPendiente@35213, FPeriodos@35232, FReferencias@35255, FTiposFactura@35280, FTiposIVA@35309, FNumeracionTipo@35336, FPendienteCtas@35359, FSaldoCtas@35379, FTipoDeAsientos@35400, FConActividad@35427, ZMensaje@35451, Eval@35485, Busca@35493, XClienteProveedor@35528, XConActividad@35565, XConDirectos@35598, XConObservaciones@35642, XContieneTexto@35665, XContieneTextoDocumento@35720, XContieneTextoObs@35765, XCuentasDiario@35801, XCuentasLbi@35850, XDeclTerceros@35885, XDeclTercerosTotal@35920, XFamilias@35942, XGeneradosPor@35979, XImporte@36016, XImporteCtas@36067, XListaNumeros@36117, XNIFDuplicado@36173, XNIFSin@36228, XNoCoincidenVtos@36250, XNumeracionNumero@36291, XNumeracionTipo@36349, XPendiente@36381, XPeriodos@36477, XPteAplicacion@36518, XPunteado@36559, XRecibosClPr@36582, XReferencias@36662, XRegistroActual@36709, XTipoArticulo@36737, XTipoCuenta@36770, XTipoDeAsientos@36802, XTiposClPr@36835, XTiposFactura@36864, XTiposIVA@36905, Registra@36955, XSegUsuarios@36968, FSegEmpresas@37005, XSegEmpresas@37029, siFiltrando@37066, MasExterno@37069, MostrarTodos@37080, XActivas@37120, FInfoAdicional@37245, XInfoAdicional@37296, XFacturado@37400, XConAjustes@37429, XMovArtTipoApunte@37456, XMovArtClienteProveedor@37489, XMovArtAlmacen@37520, FMovArticulo@37556, XMovArticulo@37572, FMarca@37606, XMarca@37645, FReferenciaAlb@37685, XReferenciaAlb@37708, FAltaLBI@37772, XAltaLBI@37783, XMinimoArticulo@37822, XCuentasVtos@37847, Init@37887, XIVAcaracteristicas@37908, FIVAcaracteristicas@37954, FEntidadTesoreria@37965, FTipoArticulo@37998, FSegUsuarios@38020, FMovArtTipoApunte@38043, FMovArtAlmacen@38069, FGeneradosPor@38083, FFamilias@38119, FTipoVencimiento@38137, XTipoVencimiento@38169, XEntidadTesoreria@38201, XContieneTextoApuntes@38234, XVencimientoUnCliente@38313, XVencimientoUnProveedor@38355, XConStockArticulo@38399, XPedido@38423, FPedido@38470, XConIVAcaja@38621

### class Trasvase  (97 métodos, 3549 líneas)

init@6747, ExportaCreaUnFichero@6755, cerrar@6839, ExportaUnBanco@6850, ExportaUnaCuenta@6863, ExportaUnCliente@6884, ExportaUnIVA@6901, ExportaUnaOperacion@6927, ExportaUnaEmitida@6949, ExportaERIVA@6987, ExportaVencimientos@7003, ExportaReferencias@7027, ExportaUnExtra@7058, ExportaUnMovBancos@7093, ExportaUnProveedor@7146, ExportaUnaRecibida@7164, importa@7196, Exporta@7291, ExportaCreaFicheros@7383, ImportaAbreFicheros@7398, ImportaAbreUnFichero@7420, ExportaFichMoneda@7489, ImportaCuentas@7492, ImportaArray2DBF@7526, ImportaBancos@7534, ImportaFichMoneda@7573, ImportaConvierte@7588, ImportaClientes@7596, ImportaSoloClientes@7606, ImportaSoloIVA@7664, ImportaSoloOperaciones@7725, ImportaSoloProveedores@7784, ImportaProveedores@7842, ImportaEmitidas@7850, ImportaSoloEmitidas@7871, ImportaSoloERIVA@7934, ImportaMiraNumero@7990, ImportaSoloVencimientos@7997, ImportaSoloReferencias@8076, ImportaRecibidas@8122, ImportaSoloRecibidas@8143, ImportaExtras@8197, ImportaMovBancos@8214, ImportaSoloExtras@8226, ImportaSoloExApuntes@8269, ImportaSoloRefApuntes@8316, ImportaSoloMovBancos@8378, ImportaSoloPagos@8433, ImportaContabiliza@8564, ExportaUnTipoVto@8598, ImportaSoloTipoVtos@8615, ExportaAjustes@8662, ImportaSoloAjustes@8677, ExportaUnArticulo@8719, ExportaUnaFamilia@8746, ExportaUnaFamiliaC@8774, ExportaUnArticuloC@8798, ImportaArticulos@8822, ImportaSoloArticulos@8832, ImportaSoloArticulosC@8922, ImportaSoloFamilias@8957, ImportaSoloFamiliasBuscaEmp@9099, ExportaUnAlbEmi@9126, ExportaApuntes@9148, ExportaUnAlbRec@9183, ExportaUnAlbPre@9206, ExportaUnAlbInv@9225, ImportaAlbEmi@9239, ImportaSoloAlbEmi@9255, ImportaSoloAlbPre@9306, ImportaSoloAlbRec@9357, ImportaSoloApuntes@9408, ImportaAlbRec@9481, ImportaAlbInv@9496, ImportaAlbPre@9511, ImportaSoloAlbInv@9527, ImportaLbi@9568, ImportaSoloLbi@9575, ExportaUnLbi@9604, ExportaUnAlbPed@9627, ExportaUnAlbPedE@9646, ImportaAlbPed@9665, ImportaAlbPedE@9681, ImportaSoloAlbPed@9697, ImportaSoloAlbPedE@9748, DameBase@9799, DameListaFicheros@9839, ExportaIA@9891, ImportaIA@9939, ExportaDiarioTxt@10015, importaDiarioTxt@10035, ExportaUnAsiento@10058, ImportaDiario@10147, ExportaAnalitica@10158, ExportaUnaActividad@10173, ImportaSoloActividades@10193, ImportaSoloAnalitica@10245

### class ControlFicheros  (31 métodos, 2233 líneas)

Cuentas@45828, error@45886, TiposOp@45906, TiposIVA@45956, Clientes@46013, Proveedores@46086, Recibidas@46175, ERIVA@46377, Bancos@46466, Extras@46505, ExApuntes@46586, MovBancos@46685, Pagos@46787, Vencimientos@46938, init@47035, InternosInicio@47040, InternosError@47046, InternosFinal@47053, fichero@47064, Muestra@47067, MuestraRegistro@47071, Procesa@47300, Lbi@47678, ParamAdmonIVA@47744, Emitidas@47773, DiarioCuentas@48009, Diario@48090, DiarioInfo@48158, Ajustes@48178, Actividades@48298, Informes@48335

### class vEMovBancos : xDDW  (26 métodos, 1253 líneas)

Init@28474, _DBF2Variables@28704, ControlErrores@28837, LaPrimeraVez@29008, TabSelect@29038, Contabilidad@29054, _Nuevo@29350, _GrabaDatos@29417, _Sigue@29574, Tools@29688, Setup2@30065, Otros@30076, LeeTrasvaseAntiguo@30446, HazTrasvase@30474, AnulaTrasvaseAntiguo@30574, Predefinidos@31069, LanzaPlantillas@31289, PostInit@31374, cadFecha@31726, FMApunte@31845, FMListaVariables@31901, FMNumApuntes@31939, FMVariable@31943, ContabilidadFusion@32044, ContabilidadFusionClaves@32061, FMIniTrabajo@32131

### class vMovBancos : xDLV  (20 métodos, 1139 líneas)

PostInit@28999, Borra@29018, Imprime@29075, Edita@29217, Otros@29259, Busca@29626, PonOrden@29764, Posicion@29808, BorraTodos@29899, RehacerDescFacturas@30105, columna@30356, PuntearTodos@30726, GridPonValor@30774, ControlSaldo@31401, CambiaTodos@31646, DatosExtImportar@31730, DatosExtRevisar@31802, DatosExtGrabar@31826, GridPreguntaColor@31999, IniciaFiltro@32079

### class vExtra : xDLV  (19 métodos, 1013 líneas)

Busca@22024, Otros@22719, Posicion@22805, Imprime@22959, CambioFechaTodas@22969, BorraTodos@23048, cTipo@23120, ImprimeYa@23384, columna@23595, Edita@23708, EntradaMultiple@23763, SumaApuntes@23777, Borra@23869, ResumenCuentas@23890, GridPonValor@24099, GridPreguntaColor@24546, CSVImportar@24558, CSVPonDocumento@24807, BotonDerecho@24920

### class vMultipleExtra : jDLVRed  (27 métodos, 971 líneas)

dbMiraRegistros@16285, GridPonValor@16382, GridSiEditamos@16456, GridPreguntaColor@16464, SaldoActual@16478, Columna@16507, Otros@16551, GridBotonDerecho@16619, InsertaPlantilla@16625, Comprobar@16684, GridPonValorCuenta@16828, GridNotas@16879, GridVtos@16901, busca@16906, GridEscape@16971, VtosGuarda@16975, VtosLee@16996, GridEdita@17027, Grabar@17089, Close@17176, inicio@17187, MiraFechaNumero@17207, EditaNumero@17241, GridDobleClick@17284, LaPrimeraVez@17288, EditaTipo@17292, PonTipo@17304

### class TB_Datos : DATAWINDOW  (27 métodos, 958 líneas)

Init@28258, PagoMas@28515, EditFocusChange@28918, TotalCambiado@28933, BuscarPagoNuevo@28964, PonerDescripcion@29546, Descripcion@29558, InformacionBorrar@29679, ImporteCambiar@29723, PendienteAplic@29875, Cuadrar@29962, Referencias@29976, ListViewMouseButtonDoubleClick@29982, Trasvase@29992, EditarOtro@30190, siCuadrado@30393, ControlesTrasvase@30397, ButtonClick@30425, SubCta@30721, VtosPtes@30904, Borrar@30949, Nuevo@30990, Predefinidos@31061, Predefinidos1@31066, CambiarNumeracion@32018, ElegirPlantilla@32023, PoncNumero@32034

### class vEExtra : xDDW  (29 métodos, 941 líneas)

Init@22260, ControlErrores@22286, _DBF2Variables@22375, Apuntes_DBF2Variable@22474, Apuntes_Variable2DBF@22559, Apuntes_EscribeLV@22562, Contabilidad@22913, _Nuevo@23140, MiraSaldosIniBancos@23316, _GrabaDatos@23471, _Sigue@23533, LeeBancos@23578, TabSelect@23691, LaPrimeraVez@24065, PostInit@24244, cadFecha@24288, Tools@24335, FMIniTrabajo@24356, FMListaVariables@24377, FMNumApuntes@24401, FMVariable@24405, FMTOTAL@24444, FMApunte@24464, _DBF2VarCopia@24847, Saldo@24938, siEstaCuenta@24956, _DBF2Variables@33065, _Nuevo@33080, _GrabaDatos@33084

### class vLbi : xDLV  (17 métodos, 890 líneas)

Borra@25493, Edita@25516, Amortizado@26612, Imprime@26779, ImpNuevoRegistro@26790, ImpFuncion@26808, Busca@26847, Otros@26942, AmortizaTodos@26960, AmortizaUno@27129, columna@27228, FR_@27564, AmortizadoExtras@28055, GridPonValor@28089, AmortizadoPeriodo@28106, AmortizadoManual@28125, Pendiente@28143

### class vParametros : JDDW  (11 métodos, 790 líneas)

Init@49166, _DBF2Variables@49206, ControlErrores@49361, _GrabaDatos@49455, _GrabaDatosTes@50924, ControlFechasDiario@51641, MiraIG@51663, CambiaDCdbf@51705, CambiaDC@51733, CambiaDC1@51830, PostInit@52237

### class ListaPagos  (30 métodos, 780 líneas)

Init@11524, Lee@11548, Graba@11574, MiraDescripcion@11627, PonValor@11673, DameValor@11677, Total@11680, NuevoDirSubcta@11688, Asiento@11704, PonTrasvase@11750, EscribeLV@11758, Borra@11799, Nuevo@11814, NumPagos@11832, bancoT@11938, ImpVariables@11942, MiraDesExt@11993, MiraDescripcionIni@12036, MiraDesEmi@12093, MiraDesRec@12122, MiraDesTra@12153, MiraDesPte@12174, MiraDesDir@12200, MiraDesCta@12220, ReiniciaDes@12235, AutoTexto@12239, MiraDescripcionDef@12255, MiraDesRem@12485, DameCliente@12722, DameProveedor@12902

### class vERemesas : xDDW  (18 métodos, 767 líneas)

Init@42716, PostInit@43100, _DBF2Variables@43501, _Nuevo@43584, LaPrimeraVez@43618, ControlErrores@43624, TabSelect@43651, Contabilidad@43667, Otros@43752, _GrabaDatos@43845, Tools@43986, FMIniTrabajo@44008, FMListaVariables@44037, FMNumApuntes@44062, FMVariable@44066, FMApunte@44117, ExportarMenu@44489, cadFecha@44692

### class vAnalitica : DATAWINDOW  (24 métodos, 694 líneas)

Init@40951, TodoPara@40990, Actividades@41044, Setup@41086, Lee@41095, ActivaGrid@41113, SetupGrid@41126, GridPonValor@41241, RehazDB@41264, BuscaAct@41330, Sym2Act@41346, Graba@41349, GridConfiguracion@41397, PantallaColDefecto@41469, MenuCommand@41482, PantallaRehacerAncho@41487, Close@41493, EliminarRepartos@41576, ReparteCuenta@42290, columna@42320, GridDobleClick@42367, ReparteCuentaActual@42372, ImporteCuentaActividad@42503, PostInit@42519

### class EdicionAsientos : Asientos  (23 métodos, 662 líneas)

CambiaTexto@3425, BorraTextoDocu@3465, MuestraLV@3535, Init@3613, Lee@3633, cBuscaTexto@3816, nBuscaTexto@3827, Mayor@4205, DatosMayor@4215, Muestra@4221, PGC@4610, Seleccionados@4743, CambiaDocu@4832, Escribe@4882, MayorCambioCuenta@4956, MayorUnaCuenta@5010, Extracto@5132, SinAjustes@5147, aListaLV@5191, NumApuntes@5330, Negativo@6071, siBuscaTextoNegativo@6101, SaldoCuenta@6236

### class ERiva  (23 métodos, 631 líneas)

Init@21237, AsociaLV@21245, Graba@21251, Mas@21340, Menos@21372, Redondeo@21385, PonSegunTotal@21410, Modificar@21494, EscribeLV@21553, SumaImportes@21592, SumaBasesMasIVADeducible@21638, aDatos@21701, aDatos@21706, PonNuevoSegunBase@21709, SumaBases@21732, DamePrimerIVA@21744, MultiIVA@21755, MasOtro@21851, SumaBasesMasIVA@21895, PonNuevoSegunTotal@21909, NuevoRegistro@21937, CambiarPulsado@21961, NumRegistros@22018

### class vActividades : xDLV  (17 métodos, 626 líneas)

GridPonValor@41029, columna@41743, Edita@41746, Borra@41763, Otros@41800, Ordenar@41811, FR_MOV@41855, ImpMovFuncion@41995, ImpMovNuevoRegistro@42032, ImpMovLeeDatos@42050, ImpMovimientosActual@42097, ImpMovCreaLO@42133, ImpMovPonSaldos@42154, ImpMovimientosTodas@42176, FR_@42612, Imprime@42649, ImpNuevoRegistro@42659

### class vConsultaVtos : xDLV  (18 métodos, 612 líneas)

ElModo@48397, columna@48403, FR_@48454, ImpFuncion@48657, ImpNuevoRegistro@48673, Imprime@48686, Otros@48717, Edita@48741, GridPonValor@48787, GridCambiaOrden@48811, Resultado@48906, FiltroFijo@48989, GridDobleClick@48992, Solo1EntoncesMarcado@49002, EligeGlobal@49008, Marcar@49032, BotonDerecho@49062, CompensarPInmediato@49095

### class TX_Datos : DATAWINDOW  (23 métodos, 594 líneas)

Init@22096, ApunteMas@22481, ApunteCambiar@22507, ApunteMenos@22535, PostInit@22872, NotasBorrar@22901, Referencias@22951, ApunteArriba@23186, ApunteAbajo@23206, EditFocusChange@23232, Ordenar@23253, BorrarTodos@23373, CambiarNumeracion@23655, PoncNumero@23660, ListViewMouseButtonDoubleClick@23715, DebeHaber@23722, ElegirPlantilla@24008, OrdenarPorCuenta@24069, ListViewKeyDown@24267, OrdenarSoloPorCuenta@24292, PoncNumero@33091, CambiarNumeracion@33095, ElegirPlantilla@33100

### class vCuentas : xDLV  (17 métodos, 587 líneas)

Edita@17450, Borra@17491, Imprime@17594, ImpNuevoRegistro@17604, saldo@17661, Otros@17668, BotonDerecho@17810, BNUApunta@18052, BorraNoUsadas@18063, Busca@18199, SetupLV@18266, columna@18270, GridCambiaOrden@18621, ImpFuncion@18940, Pendiente@18956, MiraRed@19045, CSVImportar@19124

### class TS_Datos : DATAWINDOW  (22 métodos, 576 líneas)

BuscarCuenta@42743, Nuevo@42750, Nuevo1@42811, Borrar@42814, Borrar1@42836, ImporteCambiar@42839, ImporteCambiar1@42869, InformacionBorrar@42872, Init@42978, VtosPtes@43688, ListViewMouseButtonDoubleClick@43757, EditFocusChange@43773, PonCuenta@43783, EscribeLV@43797, DirectoSubcuenta@43821, Cuenta@43837, Importe@43924, VtoMas@43936, VtoCambiar@43949, VtoMenos@43954, siVtoIgualPagos@44427, VtosCuadra@44475

### class clVtos  (30 métodos, 565 líneas)

BorraTodos@14784, CambiaCuentaDevengoDefecto@14791, Clona@14797, CreaNuevo@14810, CreaNuevoSegunCuenta@14817, EdicionAgregar@14826, EdicionAjustar@14830, EdicionEdita@14871, EdicionLV@14881, EdicionMas@14971, EdicionMenos@14991, EdicionModificar@15002, EdicionSeleccionado@15019, EdicionVentanas@15041, FMVar@15047, Graba@15077, Init@15102, Lee@15123, ListaFechas@15146, NumVencimientos@15176, PonCuentaDevengoDefecto@15187, Suma@15205, UnVto@15223, EdicionDividir@15329, LeeTPN@15397, CompruebaDBFs@15406, CreaNuevoCopia@15593, ControlFechaContable@15602, Vacia@15689, SinCuentaDevengoDefecto@15744

### class vContabilidad : DATAWINDOW  (23 métodos, 546 líneas)

Init@3325, mayor@4190, CambiaTexto@4195, CreaEnlace@4199, pgc@4605, EditFocusChange@4810, Docu@4825, BorraTextoDocu@4875, ListViewMouseButtonDoubleClick@5035, extracto@5127, FusionClaves@5256, Fusion@5766, FormEdicion@5892, FormImpresion@5897, MenuCommand@5901, FMApunte@5908, FMIniTrabajo@5966, FMListaVariables@5988, FMNumApuntes@6006, FMVariable@6010, Negativo@6064, PostInit@6118, FMVariableCuenta@6228

### class vECtaPlantillas : JDDW  (18 métodos, 519 líneas)

_GrabaDatos@39303, abajo@39336, ApunteMenos@39352, arriba@39361, BuscarCuenta@39378, columna@39388, ControlErrores@39407, GridPonValor@39457, PonCuenta@39480, Setup2@39509, Init@39660, BuscarCtaCuadre@39985, PonCuentaCuadre@39993, EditFocusChange@40007, PonImporte@40049, LaPrimeraVez@40081, BorrarCtaCuadre@40215, PostInit@40220

### class vELbiDatos : DATAWINDOW  (22 métodos, 511 líneas)

Init@25677, BusCtaElemento@25962, BusCtaDotacion@25966, BusCtaAmortizacion@25970, PonCuenta@26008, _DBF2Variables@26018, BuscarCuenta@26061, _GrabaDatos@26081, BorraCtaElemento@26103, BorraCtaDotacion@26106, BorraCtaAmortizacion@26110, EditFocusChange@26876, CambioFBajaDesdeCuadro@26937, _Nuevo@27283, PonModo@27288, DatosRecibida@27321, BusRecibida@27916, BorraRecibida@27924, BusProveedor@27928, BorraProveedor@27936, PonRecProv@27952, PostInit@27999

### class vVto : JDDW  (21 métodos, 501 líneas)

Init@13267, Setup2@13422, EditFocusChange@13460, ButtonClick@13485, EscribePagos@13500, PonRotulos@13549, BuscarEP@13586, BorrarEP@13590, BuscarCuenta@13594, BuscarCuentaCompensacion@13602, Pulsado@13613, SalvarPorDefecto@13655, PonBotonSalvar@13690, _GrabaDatos@13707, ControlErrores@13728, MismaCuentaCompensacion@13899, ListViewKeyDown@14068, ListViewMouseButtonDown@14074, LosPagosNoSeEditan@14081, MasTiposVto@15501, PostInit@15556

### class vParFacturacion : DATAWINDOW  (15 métodos, 496 líneas)

PlantAlbEmi@51310, PlantAlbRec@51314, PlantAlbPre@51318, PlantAlbInv@51322, Init@51423, PostInit@51581, PlantAlbPed@51693, PlantAlbPedE@51871, ListBoxSelect@51897, PonImpAlbaranes@51907, ListViewMouseButtonDoubleClick@51956, AlmacenesCambiarUno@51963, AlmacenesLeer@51984, AlmacenesGrabar@52004, AlmacenesMostrar@52019

### class vParCuentas : DATAWINDOW  (8 métodos, 465 líneas)

Init@49841, MirarIRPF@50089, BorrarIRPF@50097, ButtonClick@50388, PostInit@52265, BuscarPGC@52289, PonPGC@52303, MenuCommand@52310

### class RegeneraAsientos : Asientos  (11 métodos, 464 líneas)

TodosEmitidas@3669, TodosRecibidas@3699, TodosExtras@3723, TodosBancos@3748, Todos@3809, UnaRecibida@3832, UnMovBanco@3910, LeeAntiguo@4417, UnExtra@4440, UnaEmitida@4470, TodosSC@5529

### class vExApuntes : JDDW  (15 métodos, 463 líneas)

Init@24983, VtoMas@25063, VtoCambiar@25070, VtoMenos@25076, BuscarCuenta@25083, _EnBlanco@25089, ControlErrores@25136, _GrabaDatos@25184, ListViewMouseButtonDoubleClick@25218, _Array2Variables@25276, EditFocusChange@25328, MiraVencimientos@25348, BuscarCuentaBase@25406, PostInit@25425, CuentaCambiada@25431

### class clNumeracion  (19 métodos, 451 líneas)

boton@32178, antiguo@32299, nuevo@32305, graba@32321, NombrePlantilla@32950, Controles@32971, PonControles@32976, ElegirPlantilla@32997, BuscaUltimo@33038, nuevoAbono@33218, nuevaAutofactura@33250, BuscaUltimosUno@33328, PonUltimos@33357, DameUltimos@33364, QueMostrar@33367, init@33398, ComprobarNuevo@33409, BuscaUltimosTodos@33459, PonLibre@33499

### class ZI_Proveedor  (9 métodos, 447 líneas)

init@52955, ImpFuncion@52962, FR_@53017, siClave@53328, PonteRecibida@53592, PonteExtra@53733, Ponte@53756, FM_Vars@53775, PonteCuenta@53795

### class vELbiCuadro : DATAWINDOW  (16 métodos, 444 líneas)

Init@25906, Generar@26126, Borrar@26256, Nuevo@26277, _GrabaDatos@26488, ListViewMouseButtonDoubleClick@26569, Insertar@26576, Modificar@26587, EscribeLV@26648, _DBF2Variables@26675, CambioCtaDotacion@26775, CambioFBaja@26900, Baja@26924, Amortiza@27097, AmortizaUno@27157, PostInit@27987

### class ZI_Cliente  (8 métodos, 444 líneas)

init@52352, ImpFuncion@52369, FR_@52426, siClave@52726, PonteEmitida@52924, PonteExtra@53711, FM_Vars@53761, PonteCuenta@53789

### class vPlantTesoreria : JDDWumSLE  (30 métodos, 431 líneas)

Init@38719, PlNueva@38847, PlBorrar@38853, PlImportar@38863, PlOrdenar@38868, PlDuplicar@38874, Setup2@38914, BuscarImporte@38928, VtoEmitidas@38943, VtoExtras@38948, VtoProveedores@38953, VtoClientes@38958, VtoCuentas@38963, Predefinidos@38968, Trasvase@38972, DirectoCta@38977, VtoRecibidas@39002, VtosTodos@39007, _GrabaDatos@39014, Fecha@39019, Final@39023, ListViewMouseButtonDoubleClick@39029, EjecutaPlantilla@39036, EscribeLV@39055, PlEditar@39059, PteAplic@39199, DirectoCliente@39202, DirectoProveedor@39206, PostInit@39223, PulsadoEnter@39229

### class vEExPlantillas : JDDW  (15 métodos, 417 líneas)

Init@1451, ControlErrores@1499, ApunteMas@1533, ApunteCambiar@1550, ApunteMenos@1575, _EnBlanco@1779, _DBF2Variables@1790, EscribeLV@1816, Apuntes2Contenido@1838, Contenido2Apuntes@1856, _GrabaDatos@2178, ListViewMouseButtonDoubleClick@2232, abajo@2248, arriba@2266, PostInit@2339

### class vELbi : JDDW  (16 métodos, 414 líneas)

ControlErrores@26000, _DBF2Variables@26048, _GrabaDatos@26070, Init@26462, LaPrimeraVez@27278, PostInit@27300, DatosRecibida@27317, FMListaVariables@27348, FMApunte@27387, FMIniTrabajo@27449, FMNumApuntes@27466, Tools@27470, FMVariable@27488, FMPonVar@27554, FMTotAmort@27905, FMPendiente@28155

### class vPrevisionPagos : jDLVRed  (9 métodos, 394 líneas)

ImpNuevoRegistro@10296, ImpFuncion@10344, Imprime@10672, LaEntidad@11049, ElTipo@11191, columna@11207, FR_@11223, Setup2@11439, GridPonValor@11443

### class vCuentasFiltro : DATAWINDOW  (17 métodos, 386 líneas)

Borrar@17838, aFiltro@18325, BorrarGuardado@18358, Buscar@18367, Guardar@18380, Init@18405, LeeFiltro@18450, PostInit@18476, Recuperar@18488, GridConfigura@18637, GridMiraDB@18667, GridPonValor@18698, columna@18719, siTodas@18729, BienCuenta@18733, cTexto@18851, PonTexto@18874

### class xDLV : jDLVRed  (11 métodos, 382 líneas)

Comando@44695, FMApunte@44769, FMEnBlanco@44901, FMNumApuntes@44905, FMVariable@44911, FMListaVariables@44926, FMIniTrabajo@44945, FMLanza@44969, XNuevo@44991, ConfFiltro@45063, ImpFuncionColumna@45075

### class UnVto  (10 métodos, 378 líneas)

Nuevo@12960, Graba@12980, PIDirecto@13027, PICompensacion@13081, GrabaBorra@13120, GrabaContaBanco@13144, Lee@13391, NuevoSegunCuenta@13870, Clona@13879, Vacia@15678

### class CtaPlantillasControl  (17 métodos, 374 líneas)

Borrar@39765, Duplicar@39773, Grabar@39779, Importar@39795, Leer@39828, Ordenar@39832, Plantilla@39877, Replica@39880, Editar@39899, EscribeLV@39933, aNombres@39969, Ejecutar@40022, Nueva@40107, Agregar@40114, SiModelo@40178, Reordenar@40182, init@40226

### class vEIVA : JDDW  (9 métodos, 371 líneas)

Init@20134, BuscarCtaIVA@20216, BuscarCtaRE@20237, _DBF2Variables@20311, ControlErrores@20370, EditFocusChange@20395, _Nuevo@20551, _GrabaDatos@20588, PostInit@20942

### class vRemesas : xDLV  (11 métodos, 370 líneas)

Borra@43186, Busca@43206, columna@43257, Edita@43287, GridPonValor@43298, GridPreguntaColor@43317, Imprime@43330, Otros@43469, PostInit@43494, IniciaFiltro@44483, PuntearTodos@44643

### class vParFacturas : DATAWINDOW  (9 métodos, 335 líneas)

Init@51026, LanzaMenu@51170, PostInit@51209, PlantEmitidas@51296, PlantRecibidas@51300, BorrarVto@51615, BuscarVto@51619, BuscarVtoIRPF@51931, BorrarVtoIRPF@51941

### class vEBancos : JDDW  (9 métodos, 327 líneas)

Init@19438, ControlErrores@19507, BuscarCuenta@19529, _DBF2Variables@19538, EditFocusChange@19580, _Nuevo@19623, _GrabaDatos@19648, RehacerAsientos@19753, PostInit@20045

### class vENumeracion : JDDW  (10 métodos, 319 líneas)

Init@32242, Tools@32286, Setup2@32357, PonResultado@32376, EditFocusChange@32535, ListBoxSelect@32549, _GrabaDatos@32934, ControlErrores@32938, RellenaPlantilla@33279, PostInit@33386

### class vEReferencias : JDDW  (10 métodos, 315 líneas)

Init@73, ControlErrores@119, _DBF2Variables@130, Mas@171, Menos@221, EscribeLV@248, _Nueva@429, _GrabaDatos@448, BorrarTodos@700, PostInit@769

### class vParTesoreria : DATAWINDOW  (3 métodos, 315 líneas)

Init@50609, PostInit@50716, LanzaMenu@50857

### class vIVA : jDLVRed  (9 métodos, 310 líneas)

Busca@20279, Imprime@20418, ImpNuevoRegistro@20437, Edita@20455, ImpFuncion@20664, Borra@20675, Otros@20773, columna@20793, FR_@20814

### class vEApunExPlantillas : JDDW  (14 métodos, 298 líneas)

Init@1624, VtoMas@1692, VtoCambiar@1706, VtoBorrar@1726, BuscarCuenta@1742, _GrabaDatos@1759, ControlErrores@1763, _EnBlanco@1909, _Apunte2Variables@1930, VtosEscribeLV@1971, PostInit@1988, _Variables2Apunte@2146, ListViewMouseButtonDoubleClick@2239, CuentaCambiada@2345

### class vControlFicheros : JDDW  (7 métodos, 296 líneas)

Init@47173, PostInit@47485, Desmarcar@47532, Marcar@47563, _GrabaDatos@47582, Guardar@47611, GuardarC@47650

### class ListaVtos  (8 métodos, 289 líneas)

Init@14400, Menu@14405, Muestra@14456, Pendiente@14535, cerrar@14555, DameTRFX@14649, PonPendientesFiltro@14740, Releer@15506

### class vNuevoExtra : JDDWumSLE  (14 métodos, 278 líneas)

Nueva@15920, Cambiar@15924, Borrar@15933, Init@15990, Setup2@16037, _GrabaDatos@16045, LeePlantillas@16061, ControlErrores@16074, ListViewMouseButtonDoubleClick@16082, EscribeLV@16089, Edita@16114, Duplicar@16137, EligePlantilla@16161, PostInit@17331

### class vPrevisionPagosInicio : JDDW  (4 métodos, 276 líneas)

Init@10379, _GrabaDatos@10400, ControlErrores@10599, PostInit@11372

### class vELbiCuadroEditar : JDDW  (9 métodos, 276 líneas)

Init@26336, Setup2@26491, _GrabaDatos@26518, EditFocusChange@26548, Escape@26607, BuscarExtra@26684, MarcaAmort@26709, ButtonClick@26742, PostInit@27993

### class ZI_Recibida  (5 métodos, 274 líneas)

FR_@53343, siClave@53532, ImpFuncion@53537, Ponte@53604, init@53659

### class vParGeneral : DATAWINDOW  (4 métodos, 268 líneas)

Init@49628, ButtonClick@50040, Pulsado@50048, PostInit@52277

### class vRedLOG : xDLV  (6 métodos, 262 líneas)

columna@45160, Otros@45205, Imprime@45238, FR_@45256, ImpNuevoRegistro@45360, ImpFuncion@45374

### class vOperaciones : jDLVRed  (10 métodos, 244 líneas)

Busca@821, Borra@845, ImpNuevoRegistro@1070, Imprime@1088, Edita@1099, ImpFuncion@1271, Otros@1282, columna@1310, FR_@1314, Setup2@1365

### class vECuentas : JDDW  (8 métodos, 241 líneas)

Init@17359, ControlErrores@17380, _DBF2Variables@17542, _Nueva@17646, _GrabaDatos@17727, Tools@17757, LaPrimeraVez@18540, PostInit@19066

### class Asientos  (6 métodos, 236 líneas)

init@3531, Cierra@4290, Graba@4295, ReduceApuntes@5591, NumeroAsiento@6174, ErrorFechaTxt@6209

### class vETipoVtos : JDDW  (8 métodos, 236 líneas)

Init@40390, _DBF2Variables@40439, _Nuevo@40467, _GrabaDatos@40508, ControlErrores@40554, VtoBuscar@40604, VtoBorrar@40613, PostInit@40913

### class vTipoVtos : jDLVRed  (8 métodos, 215 líneas)

Borra@40245, Busca@40271, Edita@40294, ImpNuevoRegistro@40309, ImpFuncion@40327, Imprime@40339, columna@40595, FR_@40790

### class vBancos : jDLVRed  (8 métodos, 210 líneas)

Busca@19295, Edita@19324, Borra@19351, ImpFuncion@19599, ImpNuevoRegistro@19607, Otros@19728, columna@19770, Imprime@19839

### class vEOperaciones : JDDW  (8 métodos, 209 líneas)

Init@920, ControlErrores@953, BuscarCuenta@984, _DBF2Variables@1033, _Nueva@1209, _GrabaDatos@1222, PostInit@1370, CuentaCambiada@1376

### class vMayor : jDLVRed  (7 métodos, 205 líneas)

Busca@4073, Imprime@4252, ImpNuevoRegistro@4273, BotonDerecho@4653, columna@5153, Otros@5588, GridPreguntaColor@5642

### class vERiva : JDDW  (7 métodos, 201 líneas)

Init@21030, BuscarIVA@21089, _GrabaDatos@21128, ControlErrores@21144, Escribe@21183, EditFocusChange@21610, PostInit@21889

### class ZI_Emitida  (5 métodos, 201 líneas)

init@52741, FR_@52748, siClave@52867, ImpFuncion@52872, Ponte@52937

### class vPagos : jDLVRed  (6 métodos, 191 líneas)

columna@11464, ElModo@11932, FR_@12283, Imprime@12379, ImpNuevoRegistro@12391, ImpFuncion@12404

### class vReferencias : jDLVRed  (6 métodos, 190 líneas)

Busca@3, Borra@27, Edita@276, Imprime@297, Otros@715, columna@733

### class vEVtoAut : JDDW  (5 métodos, 188 líneas)

PonCVto@14191, PostInit@14224, Init@14295, _GrabaDatos@14341, DiasPago@15541

### class TipoVtos  (11 métodos, 188 líneas)

BorrarEP@40653, BuscarEP@40659, ControlErrores@40671, Graba@40698, Pon@40714, PonNuevo@40751, PonSegunCuenta@40754, PorDefecto@40759, Rotulo@40785, Lee@40851, MasTipos@40880

### class clAnalitica  (8 métodos, 187 líneas)

init@41633, Reset@41641, Lee@41644, PonEtiquetasDLV@41659, LeeDLV@41679, filMira@41712, LeeDLVext@42525, PonDB@42676

### class vEPlantillas : JDDW  (6 métodos, 185 líneas)

Init@32755, _DBF2Variables@32821, LanzaMenu@32850, _GrabaDatos@32882, ControlErrores@32913, PostInit@33392

### class vEImpExterna : JDDW  (7 métodos, 185 líneas)

Init@45422, Setup2@45497, FicheroOrigen@45505, PonProgramas@45561, ControlErrores@45586, _GrabaDatos@45593, PostInit@45794

### class fDiario  (8 métodos, 177 líneas)

BTIPO@4621, TextoMayor@5051, DocuMayor@5064, NotasOri@5670, Notas@5710, GuardaAsientoFijo@5748, LeeAsientoFijo@5759, CNUMERO@6125

### class vParDatos : DATAWINDOW  (2 métodos, 174 líneas)

Init@50220, PostInit@52271

### class vApCuentas : jDLVRed  (9 métodos, 174 líneas)

GridPonValor@53939, Otros@53968, Imprimir@53981, Importar@53993, ImpNuevoRegistro@54029, Ordenar@54049, Borrar@54076, Setup2@54085, FR_APCUENTAS@54089

### class RelacionPagos  (7 métodos, 173 líneas)

init@12528, Lee@12532, Ordena@12582, Imprime@12585, FR_@12608, ImpNuevoRegistro@12674, ImpFuncion@12688

### class vPendiente : jDLVRed  (4 métodos, 172 líneas)

Busca@14088, ImpNuevoRegistro@14139, Imprime@14156, FR_PENDIENTE@15411

### class PlConcreta  (2 métodos, 168 líneas)

Lee@15759, init@16107

### class vParCorreo : DATAWINDOW  (10 métodos, 168 líneas)

Init@52075, Setup@52114, Mostrar@52126, Leer@52150, LeerPARAM@52162, ListViewMouseButtonDoubleClick@52175, Modificar@52185, Grabar@52216, GrabarPARAM@52223, PostInit@52259

### class vExPlantillas : jDLVRed  (6 métodos, 167 líneas)

Imprime@1997, Busca@2082, Edita@2106, Otros@2201, CopiaPlantilla@2216, Borra@2326

### class vParImpresion : DATAWINDOW  (2 métodos, 161 líneas)

Init@50454, PostInit@52283

### class ActRef  (8 métodos, 160 líneas)

init@546, Edita@556, Graba@595, Caption@648, PonNuevas@726, aNuevas@730, Etiqueta@775, Lee@794

### class vERVtos : DATAWINDOW  (10 métodos, 157 líneas)

VtoMas@13907, VtoPonSegunTotal@13914, VtoMenos@13920, VtoModificar@13927, Init@13973, MiraVencimientos@14029, Setup@14037, ListViewMouseButtonDoubleClick@14044, VtoDividir@15390, PostInit@15562

### class vEOtroMovBancos : JDDW  (9 métodos, 150 líneas)

InformacionBorrar@30212, Referencias@30215, Init@30264, Setup2@30316, CopiarOrigen@30323, ControlErrores@30328, EditFocusChange@30335, _GrabaDatos@30348, PostInit@32012

### class clApCuentas  (6 métodos, 150 líneas)

init@53800, Leer@53826, Grabar@53850, Editar@53864, GrabaTabla@53921, Titulo@53957

### class vFilImporte : DATADIALOG  (5 métodos, 140 líneas)

Cancelar@34664, Init@34667, Seguir@34718, Setup2@34728, PostInit@37759

### class vPrevisionPITipo : DATAWINDOW  (7 métodos, 138 líneas)

Todos@11056, Ninguno@11059, Init@11091, PostInit@11131, Marcar@11165, DameTipos@11177, DameTodosTipos@11200

### class vNRemesa : JDDW  (7 métodos, 137 líneas)

Init@44274, BuscarCuenta@44343, BuscarBanco@44351, PostInit@44377, _GrabaDatos@44388, ControlErrores@44396, PulsadoEnter@44423

### class vPrevisionPIGeneral : DATAWINDOW  (3 métodos, 136 líneas)

Init@10785, PostInit@10879, ButtonClick@10898

### class vPlantillas : jDLVRed  (5 métodos, 134 líneas)

columna@32639, GridPonValor@32643, Edita@32676, Setup2@32694, Borra@33310

### class vBANCOS  (1 métodos, 133 líneas)

FR_@19849

### class clImpExterna  (8 métodos, 133 líneas)

init@45485, Edita@45544, Importa@45602, GrabaVariable@45630, LeeInicio@45635, Eof@45640, LeeFinal@45643, Lee@45646

### class vPrevisionPIEntidad : DATAWINDOW  (7 métodos, 132 líneas)

Todas@10921, Init@10951, PostInit@10991, Ninguna@11017, Marcar@11022, DameEntidades@11033, DameTodasEntidades@11203

### class TB_DATOS  (4 métodos, 130 líneas)

EscribeLV@28914, PonPlantilla@31335, DobleClick@31605, PonCuadre@32085

### class vPlConcreta : jDLVRed  (5 métodos, 120 líneas)

Setup2@16177, _GrabaDatos@16216, Terminar@16263, GridPonValor@16269, buscacuenta@17272

### class vFilInfoAdicional : DATADIALOG  (5 métodos, 100 líneas)

Init@37198, Setup2@37263, Cancelar@37387, Seguir@37390, PostInit@37765

### class vEFiltro : JDDW  (6 métodos, 98 líneas)

Init@34885, _GrabaDatos@34918, ControlErrores@34940, Setup2@34950, EscriveLV@34959, PostInit@37753

### class vECGeneral : DATAWINDOW  (3 métodos, 94 líneas)

Init@17879, ConsultaPGC@18017, PostInit@19076

### class vLeeImporte : DATADIALOG  (5 métodos, 84 líneas)

Init@39104, Setup@39166, Aceptar@39184, Cancelar@39192, PostInit@39217

### class vExterna : JDDW  (6 métodos, 83 líneas)

Init@45706, FicheroOrigen@45779, Guardar@45781, Recuperar@45783, BorrarGuardado@45785, PostInit@45788

### class ZI_  (3 métodos, 82 líneas)

init@53623, siClave@53665, Valor@53707

### class vCUENTAS  (1 métodos, 77 líneas)

FR_@18963

### class CtaPlantillas  (7 métodos, 75 líneas)

init@39277, PonCuentaNueva@39284, PonImporteUltimo@39291, Zap@39298, PonsiHaberUltimo@39733, PonCuadre@39748, texto@40090

### class vECPagos : DATAWINDOW  (5 métodos, 71 líneas)

Init@17957, BuscarEP@18011, BorrarEP@18014, MasTiposVto@19040, PostInit@19083

### class SLECuenta : MathiasSLE  (6 métodos, 67 líneas)

ExpandePuntos@19209, ProcessChar@19216, MiraParcial@19223, Dispatch@19246, PulsadoEnter@19260, TextValue@19271

### class MultipleExtra  (2 métodos, 63 líneas)

init@16319, Lee@16323

### class vCuentaAnalitica : jDLVRed  (3 métodos, 55 líneas)

SinRepartir@42448, GridPonValor@42473, Setup2@42480

### class clUnFiltro  (3 métodos, 49 líneas)

Texto@34100, NuevaCondicion@34116, init@34802

### class vMultiIVA : jDLVRed  (2 métodos, 43 líneas)

Setup2@21658, GridPonValor@21689

### class vCuentasFiltroDW : JDDW  (6 métodos, 41 líneas)

Init@18560, _GrabaDatos@18581, cTexto@18848, cTexto@18903, siInicialTodas@19063, QuitarTodas@19119

### class TX_DATOS  (3 métodos, 35 líneas)

Tipo2Num@22885, Num2Tipo@23874, Notas@24543

### class vLBI  (1 métodos, 34 líneas)

GridCambiaOrden@28021

### class clSaldoCuentas  (3 métodos, 30 líneas)

init@18821, DameSaldo@18825, Reiniciar@19060

### class fExtras  (3 métodos, 29 líneas)

Pendiente@23634, VtoFecha@24975, VtoFechaPte@24979

### class vDesdeHastaConta : vDesdeHasta  (1 métodos, 27 líneas)

Tools@3989

### class CtaPlantillasAp  (2 métodos, 26 líneas)

init@39251, texto@39257

### class fExApuntes  (1 métodos, 23 líneas)

Pendiente@23668

### class fCuentas  (2 métodos, 22 líneas)

PonDebeHaber@23098, PonDebeHaberIVA@23106

### class RPagosUno  (2 métodos, 21 líneas)

init@12568, banco@12715

### class TS_DATOS  (1 métodos, 17 líneas)

MiraVencimientos@43969

### class fMovBancos  (1 métodos, 16 líneas)

TEXTOREAL@30794

### class unVto  (1 métodos, 15 líneas)

ControlFechaContable@15615

### class xDDL : jDDL  (1 métodos, 6 líneas)

PostInit@45069

### class xDDW : jDDW  (1 métodos, 5 líneas)

PostInit@45058

### class clXExterna  (1 métodos, 5 líneas)

init@45774

### class vElbiCuadro  (1 métodos, 3 líneas)

CuentaDotacion@26772

### funciones/procedimientos sueltos (145)

EdicionReferencias@379(50), RefConContenido@520(26), REFAsignarTodos@653(47), LeeRotuloRef@739(30), LeeOperacion@1010(23), EdicionOperaciones@1134(54), OperacionPorDefecto@1188(21), BuscaOperacionCuenta@1292(18), NumOperacionPorDefecto@1390(61), EdicionExPlantillas@2120(26), BuscaERX@2359(65), CompruebaBancoCompVtos@2424(14), BorraER@2438(141), VtoAutomatico2Fecha@2579(119), BuscaQERB@2698(100), CPERX@2798(146), BorraTodasER@2944(57), BuscaCNumFec@3001(113), RecLBIDameRecnos@3114(18), RecLBIsiHay@3132(17), RecLBIBorra@3149(20), ConDateReal@3169(44), MiraFechaER@3213(112), CambioClaveConta@3505(26), LeeDesdeHastaConta@3953(36), DiarioTexto@4016(57), MayorUnaCuenta@4554(18), PeriodosContablesEscribe@4572(29), PeriodosContablesTool@4601(4), InformacionDiario@4668(75), BorraAsiento@4917(39), DiarioTxtDoc@5077(31), aMenuMayor@5108(19), MuestraMayor@5157(34), GeneraMayor@5336(193), PeriodosContablesEjes@5722(26), ImporteCtaAsiento@6046(18), siDiarioTxtNegativo@6109(9), FMListaVariablesCuentas@6256(32), ImporteGrupoAsiento@6288(18), Mayor_FR_@6306(163), MayorUnaCuentaCreaDB@6469(50), Mayor_FM_Apu@6519(14), PeriodosContablesMenu@6533(39), FRListaVariablesCuentas@6572(66), RenumerarAsientos@6638(109), PrevisionPagos@10630(42), PrevisionRecalculaSaldo@11397(42), RecSaldoBanco@11456(8), BusquedaPago@11836(96), MiraAutoLimpia@12266(17), MiraAutotextoBancos@12408(77), RecalculaSaldoBanco@12761(65), RecSaldoTodosBancos@12826(40), PagosEnUnPeriodo@12866(36), Vtos_Borra@13760(8), Vtos_CompruebaContaPagos@13768(9), Vtos_Descripcion@13777(40), Vtos_ConPago@13817(28), Vtos_Pendiente@13845(25), Vtos_Fecha@14051(17), Vtos_PendienteBase@14170(21), EdicionVtoAut@14364(36), Vtos_Rehaz@14558(91), Tipo2Texto@14701(12), Vtos_FechaPte@14713(27), Vtos_Pagos@15226(103), Vtos_RecalculaPendiente@15568(25), Vtos_Recalcula@15630(48), Vtos_Extra@15700(44), BuscarCuentaFT@17621(25), sCuentasImportes0@17780(15), BuscarCuentaSLEFT@17795(15), NombreCuenta@18026(12), ExisteCuenta@18038(14), EligeCuenta@18228(38), siEnFiltro@18505(35), CreaFiltroIG@18586(35), EdicionCuentas@18750(71), Texto2FiltroCuentas@18907(33), EdicionCuentasFiltro@19089(30), CuentaExpandePuntos@19276(19), EdicionBancos@19683(45), EligeBanco@19778(33), aListaBancos@19811(23), esUnaCtaBanco@19834(5), RehacerTrasferencias@19982(63), EdicionIVA@20480(49), IVAPorDefecto@20529(22), BuscaIVA@20740(33), LeeIVA@20913(25), OtroTipoIVA@20938(4), listaCuentasIVA@20948(21), BuscaIVAabr@20969(61), PonDatos@21197(40), LeeIvaFactura@21456(38), LeeIvaFacturaCC@21977(41), EdicionExtras@22637(82), Borra1Extra@23798(71), Ext1Edita@24015(50), LeeApuntesExtra@24118(50), GrabaApuntesExtra@24168(76), CopiaApuntesExtra@24960(15), EdicionLbi@25446(47), LbiLeeCuadro@26624(24), LbiLeeAmort@26728(14), LbiRehazLista@26759(13), LbiAmortiza@27020(77), LbiListaCuadro@27179(23), LbiFijaExtras@27202(13), LbiPtsEuro@27215(13), Lbi_Indice@28005(16), Borra1RegistroMB@30601(86), MB1Edita@30687(34), EdicionMovBancos@30810(94), EdicionCompVtos@31233(56), siNumBancos@32040(4), EdicionPlantillas@32566(73), CambiarNumeracion@33107(111), stBienNumeracion@33236(14), LeePago@39149(17), EdicionTipoVtos@40481(27), LeeTipoVto@40624(14), LeeTipoVtoCta@40638(15), init@40703(11), EdicionActividades@41049(37), BorraAnalitica@41502(9), AnaliticaCambiaCuenta@41511(15), LeeActividades@41526(27), LeeDatosActividad@41553(23), Analitica_lee@41591(8), Analitica_suma@41599(34), Analitica_MasCol@42562(50), EdicionRemesas@43124(62), LeeIntroRemesaNueva@44361(16), REM1Edita@44441(34), MasFormatos@44738(31), EdicionRedLog@45119(41), LeeParamControlFicheros@47654(24), siControlEmiNoIVA@48381(6), siControlRecNoIVA@48387(10), ConsultaVencimientos@48829(77), VtosPtes@48909(26), VtosPtesERX@48935(54), EditaParametros@49192(14)

## E_EdicionF  (45948 líneas)


### class TALB_DATOS : DATAWINDOW  (100 métodos, 4350 líneas)

Tools@41143, PonActualizarArticulos@41320, FacturaMenos@41335, _DBF2Variables@41349, Init@41690, F2@41979, F3@41982, F4@41985, F5@41988, F8@41991, CambiarNumeracion@41994, ElegirPlantilla@42000, PoncNumero@42006, BuscarAgente@42011, FacturaReparto@42032, FacturasPon@42081, FacturaMas@42112, FacturasClavesRepApu@42186, FacturasErrores@42207, FacturasEstado@42270, FacturasGraba@42314, FacturasLee@42399, _ActualizaArticulos@42436, _GrabaArticulos@42523, BuscarArticulos@42601, CalculaTotales@42662, CambiaCEArt@42712, CambiaCodigo@42798, CambiaEAN13@42838, cBuscarAgente@42879, columna@42907, CopiaPedido@43005, CopiaPresupuesto@43076, CreaTablaDatos@43145, EditaIVA@43206, EditaOperacion@43215, FijaAgente@43224, FMApunte@43238, FMControl@43371, FMIniTrabajo@43389, FMListaVariables@43442, FMNumApuntes@43504, FMVariable@43555, GridConfiguracion@43611, GridEsEditable@43682, GridSiEditamos@43761, GridTeclaControl@43772, ListViewMouseButtonDoubleClick@43823, MasRegistros@43834, PantallaColDefecto@43841, PantallaRehacerAncho@43858, PonActNinguno@43863, PonActTodos@43866, PonAgente@43869, PonIVAOPdef@43882, PulsadoEnter@43905, _GrabaDatos@43941, _Nuevo@44030, ControlErrores@44061, _ActualizaDctos@44188, PulsadoEscape@44241, CopiaMenu@44244, Otros@44253, CopiaEmitido@44278, CopiaRecibido@44337, CopiaPedidoE@44398, Almacen@44533, CopiaPrevios@44572, DatosCorreoPon@44607, DatosCorreoQuita@44643, PonTexto@44649, PostInit@44739, Baja@44748, VinculosPedidoMas@44819, VinculosPresupuestoMas@44854, VinculosMenos@44876, sinAgente@44894, EditarVinculo@44904, VinculosPon@44917, VinculosLee@44977, VinculosGraba@45003, VinculosLeeTipo@45049, VinculosMas@45072, F6@45091, BusqNom@45094, OtrosMenu@45149, ActualizarPrecios@45159, Close@45212, ConfigBusqueda@45223, PulsadoDelete@45228, F7@45234, CopiaInfoAdicional@45333, CambiaImporte@45347, GridPonValor@45365, GridPonValorTipo@45475, SetupGrid@45593, AnticipoClientes@45717, AnticipoProveedores@45815, AnticipoElige@45909, Anticipo@45931

### class vClientes : jDLVConBotones  (31 métodos, 2126 líneas)

Edita@16962, Borra@16977, Imprime@17228, ImpNuevoRegistro@17252, Otros@17346, CambioGeneralIVA@17605, CambioGeneralOperacion@17689, BotonDerecho@17767, EditaNuevoVarios@17886, BuscaAZ@17940, GridCambiaOrden@17969, DetBrutoNeto@17986, LanzaMenuNuevo@18027, BorraTodos@18253, EditaNuevo@18325, PulsadoBoton@18401, columna@18483, cPendiente@18501, Pendiente@18507, PendienteFiltro@18518, siDetBrutoNeto@18527, saldo@18531, TrabajoImpresion@18618, FR_CLIENTES@18622, FR_CLIENTES500@19082, ImpFuncion@19472, MiraFacturas@19557, GridPonValor@19603, GridPreguntaColor@19614, CSVImportar@19691, saldoAnticipos@19914

### class vProveedores : jDLVConBotones  (32 métodos, 1936 líneas)

Borra@20019, Imprime@20163, ImpNuevoRegistro@20187, Edita@20208, Otros@20224, BorraTodos@20673, CambioGeneralIVA@20742, CambioGeneralOperacion@20817, BotonDerecho@20886, EditaNuevo@21004, EditaNuevoVarios@21080, BuscaAZ@21112, GridCambiaOrden@21143, DetBrutoNeto@21160, Busca@21201, LanzaMenuNuevo@21258, PulsadoBoton@21263, columna@21457, cPendiente@21475, Pendiente@21480, PendienteFiltro@21492, siDetBrutoNeto@21501, saldo@21504, TrabajoImpresion@21511, FR_PROVEEDORES@21515, FR_PROVEEDORES500@21935, ImpFuncion@22272, MiraFacturas@22345, GridPonValor@22387, GridPreguntaColor@22398, CSVImportar@22475, saldoAnticipos@22673

### class EmiImpresion  (14 métodos, 1651 líneas)

ImpFuncion@7077, ImpFuncionIVA@7326, ImpNuevoRegistroIVA@7412, ImpNuevoRegistro@7462, ImpFusionClaves@7616, ImpFusionGraba@7662, skip@7755, Final@7780, Imprime@7786, init@7891, Condiciones@7895, FR_IVAREP@8685, FR_EMITIDAS@8967, SumaAlbaranes@10548

### class RecImpresion  (12 métodos, 1536 líneas)

ImpNuevoRegistro@11665, ImpFuncionIVA@12830, ImpNuevoRegistroIVA@12918, ImpFuncion@13000, skip@13340, Final@13374, Imprime@13380, init@13486, Condiciones@13490, FR_RECIBIDAS@14011, FR_IVASOP@14673, SumaAlbaranes@16157

### class vArticulos : jDLVconBotones  (25 métodos, 1365 líneas)

Busca@153, Borra@767, Edita@800, Imprime@825, Otros@1585, Recalcular@1650, columna@1794, ImpNuevoRegistro@1858, ImpFuncion@1871, ListaPresupuestos@2057, RehacerDctos@2164, GridCambiaOrden@2256, CambioGlobal@2788, VerMovimientosUno@3123, VerMovimientosTodos@3166, PulsadoBoton@4058, BuscaAZ@4063, GridPonValor@4092, GridPreguntaColor@4118, CSVImportar@4125, EligeGlobal@4361, BotonDerecho@4429, VerResumen@4485, Marcar@4606, CambioGlobalIVA@4671

### class vEArticulos : xDDW  (35 métodos, 1323 líneas)

Init@389, _DBF2Variables@856, ControlErrores@956, _GrabaDatos@973, _Sigue@1032, PonFamilia@1052, PonProveedor@1092, SetupGrid@1103, GridPonValor@1154, BuscarFamilia@1160, BuscarProveedor@1166, Otros@1180, QuitarProveedor@1186, QuitarFamilia@1192, EditarFamilias@1249, PonDctoVenta@1258, EditFocusChange@1266, ButtonClick@1298, BuscarOperacionC@1370, BuscarIVAC@1380, BuscarIVAV@1419, BuscarOperacionV@1431, PonIVAV@1443, PonIVAC@1479, PonOperacionV@1515, PonOperacionC@1550, PostInit@1781, Foto@2028, RehacerDctos@2093, PonDctoCompra@2151, BuscarFamiliaA@2244, VerMovimientos@2877, Recalcular@2897, ErrorEnCodigo@4387, _Copia@4444

### class vERecibidas : xDDW  (23 métodos, 1323 líneas)

Init@10959, ControlErrores@11374, Contabilidad@11456, PonProveedor@11543, _DBF2Variables@11691, _Nueva@11871, _GrabaDatos@12070, _Sigue@12215, TabSelect@12651, PostInit@13211, MiraTabs@13251, MiraVencimientos@13264, MuestraOperacion@13329, Otros@13365, _NuevaFact@13551, Tools@13998, cadFecha@15075, PaginaDatos@15079, OtrosLbi@15082, OtrosIVARepercutido@15125, ControlAlCancelar@15152, LaPrimeraVez@16137, CopiaInfoAdicionalAlbaran@16167

### class vEInventarios : xDDW  (51 métodos, 1319 líneas)

Init@26984, PoncNumero@27074, _Nuevo@27079, CreaTablaDatos@27095, SetupGrid@27138, _DBF2Variables@27228, GridBotonDerecho@27271, PantallaColDefecto@27282, Otros@27300, GridTeclaControl@27322, CambiarNumeracion@27372, ElegirPlantilla@27378, GridPonValor@27384, BuscarArticulos@27421, CambiaCEArt@27451, CambiaCodigoEAN13@27491, _GrabaDatos@27527, ControlErrores@27559, _GrabaArticulos@27572, F2@27652, F3@27656, F4@27659, F5@27662, F8@27665, PulsadoEnter@27678, GridConfiguracion@27727, Tools@27798, PantallaRehacerAncho@27819, Close@27825, FMListaVariables@27838, FMIniTrabajo@27864, FMApunte@27871, FMNumApuntes@27924, FMVariable@27952, columna@27984, _ActualizaArticulos@28075, _ActualizaDctos@28108, GridEsEditable@28144, ControlErroresArt@28150, Almacen@28194, ImporteActual@28237, ImporteSuma@28244, PonImporteSuma@28261, NumApuntes@28265, PostInit@28287, F6@28293, CambiaNumApuntes@28298, BusqNom@28375, PulsadoDelete@28412, PulsadoEscape@28417, F7@28421

### class vAlbaranes : xDLV  (23 métodos, 1319 líneas)

Borra@37471, Busca@37491, CalculaBII@37498, CambioDecimales@37507, columna@37536, Edita@37635, FR_ALBEMI@37641, FR_ALBPED@37800, FR_ALBPEDE@37929, FR_ALBPRE@38058, FR_ALBREC@38203, GridPonValor@38374, GridPreguntaColor@38394, ImpFuncion@38403, ImpNuevoRegistro@38421, Imprime@38434, Otros@38470, Setup2@38524, AnchoMaximo@38653, FR_BASE@38750, BorrarTodos@38887, numLineasAlbaran@38929, Marcar@39142

### class CalculaFact  (56 métodos, 1262 líneas)

base@28469, cIVA@28479, DctoComBase@28530, DctoComImporte@28536, DctoComPorc@28542, DctoPPBase@28550, DctoPPImporte@28557, DctoPPPorc@28563, EligeIVA@28571, EligeOperacion@28604, EtiquetaIVA@28649, EtiquetaOperacion@28682, IniFactura@28700, IRPFBase@28723, IRPFImporte@28726, IRPFPorc@28730, iva@28733, LeeIVAs@28749, LeeOperaciones@28783, MasAlbaran@28821, MasBloque@28967, LeeAlbaran@29187, total@29246, PonEriva@29255, FMVarDctoCom@29290, FMVarDctoPP@29307, FMVarIRPF@29325, cpi@29379, db@29403, ApunteValido@29409, NumApuntes@29423, PonIVAOpDef@29899, CreaDB@30065, init@30181, BaseIVA@30243, PorcentajeIVA@30278, FMApunteArt@30295, AumentoBase@30415, AumentoImporte@30421, AumentoPorc@30427, RetencionBase@30435, RetencionImporte@30441, RetencionPorc@30447, AumentoTotal@30455, RetencionTotal@30464, FMVarAumento@30473, FMVarRetencion@30492, IRPFConcepto@30511, AumentoConcepto@30515, RetencionConcepto@30522, FMVarSuplido@30541, SuplidoImporte@30556, SuplidoConcepto@30562, SuplidoTotal@30569, ctaAnticipoCrear@30712, PonApuntes@30716

### class vEFacturacion : DATAWINDOW  (36 métodos, 1228 líneas)

Init@30937, Mas@31072, Nuevo@31324, Modificar@31341, FMIniTrabajo@31387, FMListaVariables@31391, FMTools@31471, Setup@31504, PonAlbaranes@31525, LeeAlbaranes@31531, EscribeLV@31541, Menos@31587, ListViewMouseButtonDoubleClick@31601, CalculaTotales@31608, Arriba@31675, Abajo@31687, FMNumApuntes@31703, FMControl@31742, FMVariable@31773, FMApunte@32000, Columna@32084, _GrabaAlbaranes@32191, Reinicia@32196, FMDatosAlbaran@32226, FMVariableFact@32767, FMInicio@32852, CambiarFactura@32901, DatosCorreoPon@32960, DatosCorreoQuita@32980, PostInit@32987, OrdenarFechaMas@32997, OrdenarFechaMenos@33006, OrdenarLibre@33023, FMNotasAlb@33105, CopiaObservaciones@33126, DameCalculaFactTotal@33160

### class vFamilias : DIALOGWINDOW  (41 métodos, 1189 líneas)

Init@35057, Grabar@35266, TreeViewMouseButtonDown@35286, ExpandOneLevel@35301, CollapseOneLevel@35306, ExpandBranch@35311, Dispatch@35318, TreeViewDragBegin@35354, TreeViewDragEnd@35390, TreeViewDragMove@35434, TransferItem@35471, PonMover@35512, CollapseBranch@35522, Nuevo@35543, EsAntepasadoDe@35613, Borrar@35634, n2s@35657, ExpandItems@35660, ControlErrores@35678, MenuCommand@35682, Close@35738, NuevoHermano@35747, NuevoHijo@35750, ExpandNivel@35756, RehazTV@35770, PonVisible@35835, TreeViewMouseButtonDoubleClick@35841, Comando@35855, ElPadreDe@35892, EditaCabecera@35903, ApunteEnBlanco@35929, Editar@35948, Buscar@35994, Setup@36058, TextoElem@36343, GeneraLista@36357, GeneraListaDesde@36367, MiraNumeros@36402, lista2num@36548, num2lista@36551, CompruebaLista@36853

### class vEEmitidas : xDDW  (21 métodos, 1124 líneas)

Init@5629, ControlErrores@5719, PonCliente@5826, TabSelect@5839, Contabilidad@5877, _GrabaDatos@6116, _Sigue@6238, _Nueva@6308, PostInit@7492, MiraVencimientos@7534, MuestraOperacion@7600, _DBF2Variables@8024, _NuevaFact@8198, Tools@8327, cadFecha@9681, PaginaDatos@9685, Otros@9688, OtrosIVASoportado@9696, LaPrimeraVez@10529, CopiaInfoAdicionalAlbaran@10558, OtrosPython@10681

### class vEmitidas : xDLV  (21 métodos, 1073 líneas)

Borra@5224, Busca@5227, Imprime@5993, Edita@6000, Otros@6010, MostrarImporteClientes@6499, ListadoPorClientes@6623, BorraTodas@6890, CambioFechaTodas@6895, FMImpresion@7548, Agente@7557, Autofactura@7571, Fusion@7727, Facturar@7985, Asociar@8008, GridCambiaOrden@8445, columna@8473, GridPonValor@8518, ImpresionContinua@8558, GridPreguntaColor@9705, RelacionCobros@9727

### class vRecibidas : xDLV  (18 métodos, 870 líneas)

Borra@11363, Busca@11367, Edita@11861, MostrarImporteProveedores@12290, ListadoPorProveedores@12415, BorraTodas@12705, CambioFechaTodas@12709, Imprime@12821, FMImpresion@13285, Agente@13298, Facturar@13686, Asociar@13712, GridCambiaOrden@13831, columna@13865, GridPonValor@13909, GridPreguntaColor@15138, Otros@15178, RelacionPagos@15272

### class clGenRecibos  (11 métodos, 811 líneas)

Generar@33418, LeeClavesAntiguas@33502, LeeClavesAgentes@34081, EditaClaves@34104, BuscaClaves@34193, EditaClavesDLV@34410, GuardaClaves@34514, GeneraFactAlb@34538, GenEmitida@34586, GenAlbaranEmi@34716, GenRecibida@34870

### class clAlbaranes  (14 métodos, 699 líneas)

init@29448, eligeLibres@29497, PonIndFactura@29670, LeeLista@29689, GrabaFacturaRep@29754, MiraApuRepartos@29839, LeeFacturas@29860, PonIndAlbaran@29894, PonFacturaYReparto@29919, GrabaFactura@29980, sAlb@30274, eligeAgente@30346, Eval@30398, CalculaTotalesFactura@30610

### class vNRecibidasP : JDDWumSLE  (22 métodos, 646 líneas)

Init@15439, Setup2@15584, BuscaProveedor@15620, PonProveedor@15632, CompruebaAnticipos@15731, TrasPulsarEnter@15771, _GrabaDatos@15805, AnticiposCompensar@15844, BorrarEP@15870, BuscarEP@15873, ControlErrores@15876, EditFocusChange@15908, ListBoxSelect@15936, MasTiposVto@15948, MenuAnticipos@15953, PorDefecto@15979, RecalculaVto@15982, sinPagos@16003, sinPagosBaja@16037, ConfigBusqueda@16112, tools@16116, PostInit@16173

### class clStock  (15 métodos, 631 líneas)

VisCerrar@2936, VisCreaDB@2941, Visualizar@2978, RecalculaCompleto@3009, BuscaUltInvTotal@3038, init@3053, RecalculaUno@3058, ImprimirTodos@3606, FR_Niveles@3624, FR_@3702, ImpTNuevoRegistro@3957, ImpTFuncion@3972, TipoPreformato@4015, RecalculaLista@4635, nivel@5214

### class vNEmitidasC : JDDWumSLE  (22 métodos, 600 líneas)

Init@9870, _GrabaDatos@9985, AnticiposCompensar@10039, BorrarEP@10065, BuscarEP@10068, CompruebaAnticipos@10071, ControlErrores@10111, EditFocusChange@10131, ListBoxSelect@10152, MasTiposVto@10164, MenuAnticipos@10169, PorDefecto@10195, PostInit@10199, RecalculaVto@10205, sinPagos@10226, sinPagosBaja@10253, tools@10264, TrasPulsarEnter@10278, PonCliente@10313, BuscaCliente@10417, setup2@10431, ConfigBusqueda@10464

### class TE_Datos : DATAWINDOW  (27 métodos, 593 líneas)

Init@5349, BuscarCliente@5655, VtoMas@5692, VtoModificar@5699, VtoMenos@5706, ListViewMouseButtonDoubleClick@6604, IvaMas@6764, IvaMenos@6770, IvaCambiar@6776, IvaRedondeoMas@6796, IvaRedondeoMenos@6802, IvaPonSegunTotal@6820, NotasMenos@6850, BuscarOperacion@6858, Referencias@6870, PoncNumero@6878, CambiarNumeracion@6884, VtoPonSegunTotal@7019, TipoCuenta@7583, ElegirPlantilla@7976, PonTotalDecl@8634, totalDecl@8651, ListBoxSelect@8667, VtoDividir@8678, totalDeclTotal@9699, PostInit@9721, PonLibre@10541

### class EmiImpRegistro  (7 métodos, 560 líneas)

ImpFuncion@40050, ImpFuncionIVA@40121, ImpNuevoRegistro@40194, init@40241, skip@40245, FR_@40262, Imprime@41034

### class clResumenArt  (7 métodos, 558 líneas)

init@4496, ImpNuevoRegistro@4500, hazArticuloActual@4514, imprime@4588, FR_@4766, ImpFuncion@5131, parametros@5162

### class vEClientes : xDDW  (9 métodos, 545 líneas)

Init@17054, _DBF2Variables@17080, _Nuevo@17273, _GrabaDatos@17439, Tools@17872, LaPrimeraVez@18153, ControlErrores@18160, PonNuevaCuenta@19589, PostInit@19621

### class vEProveedores : xDDW  (8 métodos, 536 líneas)

Init@19993, ControlErrores@20058, _Nuevo@20301, _GrabaDatos@20363, LaPrimeraVez@20519, _DBF2Variables@20531, PostInit@22405, Tools@22683

### class vMovArt : xDLV  (8 métodos, 533 líneas)

columna@39261, Albaran@39322, FiltroDame@39366, nAgente@39383, FR_@39421, Imprime@39723, ImpNuevoRegistro@39749, ImpFuncion@39762

### class TR_Datos : DATAWINDOW  (22 métodos, 531 líneas)

Init@11129, PoncNumero@11620, CambiarNumeracion@11627, ListViewMouseButtonDoubleClick@12396, IvaMas@12574, IvaMenos@12580, IvaCambiar@12586, IvaPonSegunTotal@12606, IvaRedondeoMas@12623, IvaRedondeoMenos@12629, NotasMenos@12641, Referencias@12697, VtoPonSegunTotal@12958, TipoCuenta@13312, ElegirPlantilla@13545, ListBoxSelect@13947, PonTotalDecl@13956, totalDecl@13973, VtoDividir@13989, totalDeclTotal@15132, PonLibre@16149, PostInit@16179

### class clImpFacturas  (13 métodos, 518 líneas)

FMApunte@32286, FMControl@32366, FMListaVariables@32395, FMNumApuntes@32465, FMVariable@32504, init@32584, columna@32599, LeeFactura@32671, FMIniTrabajo@32763, FMVariableFact@32782, MiraSiFactura@32795, FMDatosAlbaran@32885, FMVariableCuenta@33019

### class RecImpRegistro  (7 métodos, 506 líneas)

FR_@40528, ImpFuncion@40805, ImpFuncionIVA@40855, ImpNuevoRegistro@40929, init@40962, skip@40966, Imprime@40983

### class vARTICULOS  (1 métodos, 489 líneas)

FR_@2275

### class TC_NFACT : DATAWINDOW  (15 métodos, 424 líneas)

AjustesCambiar@23968, AjustesMas@23974, AjustesMenos@23980, BorrarEP@23984, BuscarEP@23988, BuscarIVA@23992, BuscarOperacion@24004, ButtonClick@24015, Init@24054, ListViewMouseButtonDoubleClick@24175, PonIVA@24182, PonOperacion@24218, Setup@24356, MasTiposVto@24622, PostInit@24793

### class Contactos  (14 métodos, 402 líneas)

Muestra@22739, Mas@22767, Menos@22770, Cambiar@22783, Edita@22792, Contenido@22846, EditaCtaFact@22854, FiltrarMal@23542, FiltrarBien@23555, init@23568, Elementos@23629, ValorLista@23633, Borrar@23641, BotonDerecho@24370

### class TC_BASE : DATAWINDOW  (14 métodos, 397 líneas)

BuscarCuenta@23689, ContactosCambiar@23703, ContactosMas@23709, ContactosMenos@23715, EditFocusChange@23719, Init@23737, ListViewMouseButtonDoubleClick@23888, Referencias@23895, Foto@24576, PostInit@24718, BuscarCuentaAnticipos@24817, BuscaCodPostal@24822, GuardarCodPostal@24858, CuentaCambiada@25244

### class vAjustes : DATAWINDOW  (16 métodos, 352 líneas)

Init@25714, Mas@25778, Menos@25782, Cambiar@25786, Setup@25827, MiraAsientos@25846, pgc@25880, EdicionAsiento@25889, numMasAsientos@25896, mayor@25899, mayorUno@25925, MuestraMayor@25957, ListViewMouseButtonDoubleClick@26016, ActualizarSaldos@26025, Sigue@26573, PostInit@26744

### class InfoEmitida  (12 métodos, 347 líneas)

cerrar@10580, write@10597, init@10600, vencimientos@10611, facturacion@10640, grabar@10713, emitida@10741, cuentas@10753, iva@10769, empresa@10790, cliente@10834, situate@10873

### class vAutofacturas : JDDW  (7 métodos, 331 líneas)

Init@16227, Nueva@16253, Antigua@16274, _GrabaDatos@16311, ControlErrores@16387, _DBF2Variables@16693, PostInit@16853

### class clRecibos  (18 métodos, 331 líneas)

Abajo@33553, AgregaClaves@33566, Arriba@33619, BorraActual@33632, concepto@33642, Edita@33650, EditaActual@33665, EditaNuevo@33673, eje@33677, Grabar@33683, importe@33736, init@33742, Leer@33751, mes@33782, MuestraLV@33788, PonLV@33821, rseparado@34831, CopiaActual@34842

### class vApuntesER : JDDW  (11 métodos, 330 líneas)

ControlErrores@25513, _GrabaDatos@25536, BuscarCuenta@25555, EditFocusChange@25562, Init@25620, ButtonClick@25800, Pulsado@25808, Setup2@26090, PostInit@26750, PonCuenta@26756, CuentaCambiada@26774

### class clBusquedaCP  (5 métodos, 326 líneas)

BuscaClientes@24901, init@25010, Configura@25036, siCon@25097, BuscaProveedores@25101

### class vInventarios : jDLVRed  (8 métodos, 286 líneas)

Busca@26864, columna@26870, Edita@26881, Borra@27608, Otros@27690, LanzaMenuNuevo@28038, EditaUno@28043, CambiaTipo@28327

### class clFamilias  (17 métodos, 281 líneas)

MiraMenu@36670, LanzaMenu@36705, TieneHijos@36718, init@36728, BuscaMenu@36731, PreparaMenu@36735, DameMenuLista@36740, Editar@36751, MiraDescuento@36763, AltLista@36784, MiraLista@36801, ListaHijos@36824, ListaDescuentos@37154, aListaOrdenada@37177, EligeUna@37197, TextoUna@37227, LeerFichero@37246

### class vLibroRegistro : JDDW  (4 métodos, 256 líneas)

Init@39794, ControlErrores@39899, _GrabaDatos@40005, Setup2@40016

### class vGenRecibos : JDDW  (5 métodos, 250 líneas)

Init@33249, ControlErrores@33364, _GrabaDatos@33393, PostInit@34864, Setup2@34982

### class vContactos : JDDW  (9 métodos, 231 líneas)

Init@23017, BorrarVto@23106, BuscarVto@23110, BuscarCuenta@23120, _GrabaDatos@23135, ControlErrores@23151, Setup2@24751, PostInit@24799, CuentaCambiada@25227

### class ApuntesER : BaseApuntesER  (11 métodos, 227 líneas)

EscribeLV@25345, Mas@25405, Menos@25422, Modificar@25437, Lee@25461, Seleccionado@25465, Ventanas@25840, tipo@25892, AsientoApunte@25992, Edita@26623, Agregar@26641

### class vEFamilias : JDDWumSLE  (10 métodos, 226 líneas)

Init@36216, ControlErrores@36254, _GrabaDatos@36264, GridPonValor@36396, _DBF2Variables@36415, SetupGrid@36435, PonNoEditables@36492, GridSiEditamos@36524, GridPreguntaColor@36533, PostInit@37240

### class vERecibos : JDDW  (7 métodos, 219 líneas)

_GrabaDatos@33868, ButtonClick@33889, Init@33898, MiraMarcados@33963, MiraUnMarcado@33971, Setup2@33985, PostInit@34858

### class clFoto  (12 métodos, 200 líneas)

init@37271, BotonPulsado@37293, Muestra@37315, Cambia@37328, Grabar@37334, Directorio@37383, CompruebaCarpetas@37398, Nueva@37407, Borra@37435, siMostrando@37442, Axit@37445, CompruebaCarpeta@37453

### class TA_Datos : DATAWINDOW  (9 métodos, 199 líneas)

Init@16514, BuscaIvaRepercutido@16635, BuscaProveedor@16652, BuscaIvaSoportado@16664, Referencias@16727, PoncNumero@16830, CambiarNumeracion@16835, ElegirPlantilla@16841, PostInit@16863

### class vEAlbaranes : xDDW  (11 métodos, 196 líneas)

Init@41116, FijaAgente@43937, _GrabaDatos@44007, _DBF2Variables@44018, ControlErrores@44085, Tools@44089, SetupAlb@44102, PostInit@44156, TabSelect@44177, Otros@44275, CambiaNumApuntes@44783

### class TC_BANCO : DATAWINDOW  (5 métodos, 192 líneas)

Init@18068, PostInit@18537, Auxiliar@18549, EditFocusChange@18605, Pon24Digitos@19967

### class vImpresionER : JDDW  (9 métodos, 187 líneas)

Init@26384, PostInit@26449, _DBF2Variables@26461, _GrabaDatos@26467, ButtonClick@26480, Pulsado@26492, ControlErrores@26537, NoAutofacturas@26604, SiRegistro@26607

### class vFamiliasLista : vFamilias  (4 métodos, 143 líneas)

Setup@36903, Editar@36984, Grabar@37099, Close@37112

### class TC_RECIBOS : DATAWINDOW  (9 métodos, 138 líneas)

Abajo@34283, Arriba@34286, Cambiar@34289, Init@34292, ListViewMouseButtonDoubleClick@34373, Mas@34380, Menos@34383, Copiar@34837, PostInit@34852

### class vERVarios : jDLVRed  (4 métodos, 127 líneas)

GridPonValor@26285, columna@26290, buscacuenta@26321, Setup2@26800

### class vStock : jDLVRed  (5 métodos, 119 líneas)

Busca@1677, ImpNuevoRegistro@1715, Imprime@1728, columna@1742, ImpFuncion@3108

### class vCPOcasional : JDDW  (6 métodos, 119 líneas)

Init@23371, BuscarCuenta@23477, _GrabaDatos@23485, ControlErrores@23490, PonCuenta@23533, PostInit@24805

### class jDLVconBotones : xDLV  (6 métodos, 118 líneas)

ButtonClick@24458, IniBotones@24470, NuevoBoton@24488, PantallaPonControles@24494, PonBotones@24500, PonLetras@24562

### class vAutoFacturas  (4 métodos, 112 líneas)

TabSelect@16682, Contabilidad@16733, Contabilidad@16778, cadFecha@16849

### class clConfigAlbaranes  (3 métodos, 108 líneas)

init@38545, Salto@38584, ValorDB@38638

### class TR_DATOS  (7 métodos, 101 líneas)

VtoMas@11556, VtoModificar@11563, VtoMenos@11570, BuscarOperacion@11577, BuscarProveedor@11590, EditFocusChange@11635, MiraVencimientos@13278

### class menuFamilias : Menu  (1 métodos, 95 líneas)

Init@35171

### class ImpEtiquetas  (4 métodos, 87 líneas)

init@30089, PonNumEtiquetas@30110, NumEtiquetas@30149, Siguiente@30163

### class TP_IRPF : DATAWINDOW  (2 métodos, 83 líneas)

Init@21305, BuscarIRPF@21346

### class TE_DATOS  (3 métodos, 80 líneas)

EditFocusChange@5963, MiraVencimientos@7030, ControlaAbonos@7982

### class ClPrNuevaCuenta  (3 métodos, 80 líneas)

ControlErrores@24638, Cuenta@24673, init@24713

### class MenuFamiliasLista : Menu  (1 métodos, 75 líneas)

Init@37024

### class AlbjGridE : jGridE  (3 métodos, 65 líneas)

FocusChange@41192, Init@41219, PonteSiguienteEditable@41231

### class vGenRecClaves : jDLVRed  (1 métodos, 59 líneas)

Setup2@34224

### class vCLIENTES  (1 métodos, 51 líneas)

Busca@16911

### class TA_DATOS  (2 métodos, 42 líneas)

EditFocusChange@16869, PonImporteIVA@16886

### class ICOELEGIR : Icon  (1 métodos, 33 líneas)

Init@37121

### class ICOFAMILIA : Icon  (1 métodos, 6 líneas)

Init@36557

### class vImpEtiquetas : jDLVRed  (1 métodos, 5 líneas)

GridPonValor@30144

### class ICOCADENA : Icon  (1 métodos, 3 líneas)

Init@36563

### funciones/procedimientos sueltos (95)

EdicionArticulos@1(152), LeeArtCaracteristicas@1198(16), GrabaArtCaracteristicas@1214(35), Suma3Dctos@1671(6), NumeroAlb@1941(29), AgenteAlb@1970(40), LeeArticulo@2010(18), Suma2Dctos@2090(3), CalculaPVenta@2764(24), VisTomaDatos@3230(376), EligeAlmacen@4019(39), Emi1Edita@8339(106), EdicionEmitidas@9579(102), LeeIntroEmitidaNueva@10470(59), Rec1Edita@13727(83), RecibidaRepetida@13810(21), EdicionRecibidas@14976(99), LeeIntroRecibidaNueva@16054(58), LeeClienteCuenta@17921(19), LeeCliente@18437(18), MenuClientes@18455(28), MailCliente@19592(11), EdicionClientes@19636(55), ClienteSegunCuenta@19899(15), Form24Digitos@19945(22), LeeProveedorCuenta@20986(18), LeeProveedor@21388(18), MenuProveedores@21406(51), MailProveedor@22376(11), EdicionProveedores@22420(55), ProveedorSegunCuenta@22701(15), IRPFProveedor@22716(23), LeeContacto@22922(95), CambioGlobalCNF@23183(188), CPMenuNuevoLanza@23413(60), CPMenuNuevoResultado@23473(4), LeeContactosCNF@24442(16), FRCliProvExtra_@24581(41), MailContacto@24736(15), CambioGlobalEP@25255(49), ControlClPr@25304(27), TelefonoContacto@25331(14), ERLeeCtasAutom@26142(143), aCambioAsiento@26552(21), FR_ColumnasIVA@26648(69), FR_MiraIVA@26717(27), EdicionInventarios@26828(36), CalculaImporte@29114(28), MasRegistros@29142(21), Redondea@29163(3), PlantFactura@29166(21), AlbColDLV@29341(38), AlbTextoImprimir@30199(22), TiposApunte@30221(22), PonDecQ@30258(8), PonDecP@30266(8), DescuentaPrecio@30404(11), FMCaracteristicasPon@30578(11), FMCaracteristicasSiEs@30589(3), FMCaracteristicasValor@30592(18), PantallaRehacerAncho@30650(26), LineaAlbaranEmitido@30676(36), txtPedidos@30798(40), Descuenta@30838(99), FMLisClientes@31118(51), FMLisProveedores@31169(42), FMLisIRPF@31211(12), FMLisDctos@31223(57), FMLisIVA@31280(18), FMLisNotas@31298(26), FMVarProveedor@31856(48), FMVarCliente@31904(72), FMSumaYsigue@31976(24), FMLisVto@32177(14), FMIniTrabajoDLV@32204(22), FMAlbTitulos@32799(53), FactFMIniTrabajo@32924(36), FMLisNotasAlb@33095(10), FMAlbTituloVar@33168(81), TipoDctos@36297(12), cTipoDctos@36309(23), EdicionFamilias@36332(11), LeeFamilia@36566(16), LeeCaracteristicas@36582(36), GrabaCaracteristicas@36618(52), TipoArticulos@36840(13), VinculoHijo@38696(54), VinculoPadre@38803(43), Borra1Alb@38846(41), EdicionAlbFact@38968(174), EdicionMovArt@39210(51), ALbAcumArticulos@41257(63), Edita1Albaran@44468(65), AlbGrabaApuntes@45239(68), BajaUno@45307(26)

## F_Contabilidad  (23661 líneas)


### class impInformes  (34 métodos, 2480 líneas)

Init@12551, EsImporteErroneo@12560, x21_ExpandeCuentasLista@12563, x211_ExpandeCuentasGrupo@12621, x2111_ExpandeCuentasUna@12632, x221_CalculaLista@12745, x222_CalculaLinea@12759, x3_ClaveGrabar@12938, x3_ClaveLeer@12959, x2221_Cuentas@12978, x23_PonTotalesOperacion@13086, x01_PreparaCalculo@13224, x231_CalculaColumnas@13267, x41_NuevoRegistro@13316, x41_Funcion@13360, x24_PonDCONyHaber@13408, x21111_ExpandeCuentasTexto@13541, x4_Imprime@13600, x2_PreparaInforme@13616, x4_Fusiona@13709, FusionarNotepadClaves@13740, FusionarInicio@13888, FusionarFinal@13893, x0_ColumnasLee@14444, x22_CalculaGrupo@14504, x11_LeeDiario@15030, x12_LeeDiarioActiv@15125, x1_AgregaCuentas@15238, x41_Columnas@15662, x0_Comprueba@15846, x11_ACImporte@15981, x21111_SumaPorTipoAs@16004, Imprime@16098, x4_Exporta@16222

### class vApuntes : DIALOGWINDOW  (47 métodos, 1745 líneas)

Init@4807, Grabar@4830, TreeViewMouseButtonDown@4865, ExpandOneLevel@4880, CollapseOneLevel@4885, ExpandBranch@4890, Dispatch@4897, TreeViewDragBegin@4933, TreeViewDragEnd@4969, TreeViewDragMove@5012, TransferItem@5049, PonMover@5100, CollapseBranch@5110, Nuevo@5131, EsAntepasadoDe@5208, Borrar@5229, n2s@5249, ExpandItems@5252, Setup@5434, ControlErrores@5548, MenuCommand@5601, Close@5657, NuevoHermano@5687, NuevoHijo@5690, ExpandNivel@5708, RehazTV@5722, PonVisible@5756, TreeViewMouseButtonDoubleClick@5762, Comando@5779, GeneraLista@5972, GeneraListaDesde@5982, ElPadreDe@6026, EditaCabecera@6037, ApunteEnBlanco@6063, Editar@6101, EditaSaltoPagina@6148, EditaSeparacion@6169, CGMargenes@6205, CGCondicion@6270, CGListaCuentas@6309, jLeeBuscar@6359, Otros@6373, NotepadClaves@6399, EligeTipo@6425, Buscar@6440, Copiar@6558, NotepadTodo@6587

### class LibrosRegistro  (20 métodos, 1537 líneas)

AdjudicaLineaIva@2193, init@2357, MarcaFechas@2368, NuevoRegistro@2403, NuevoRegistroIVA@2438, NuevoRegistroNoFact@2472, NuevoRegistroFact@2509, ResumenVentas@2625, ResumenCrea@2647, imprime@2710, NuevoResumen@2739, ResumenCompras@2753, ResumenImprime@2776, FR_LREGISTROC@2805, FR_LREGISTROV@3094, FR_LRESUMENC@3383, FR_LRESUMENV@3527, Funcion@3671, compras@3886, ventas@3900

### class ResumenIVA  (9 métodos, 1309 líneas)

Init@1011, ControlFicheros@1015, LeeDatos@1042, Imprimir@1259, GeneraAsientoIVA@1788, Procesa@1973, MiraIVABX@2007, MiraIVADevolverAnterior@3813, DeterminaFechas@4051

### class ImprimirMayor  (17 métodos, 1080 líneas)

imprimir@11106, ImpNuevoRegistro@11128, Datos@11388, init@11692, ImpNuevoAcumular@11771, ImpFuncion@11834, FR_XMAYOR@11991, DameImporte@12213, FMIniTrabajo@12251, FMListaVariables@12268, FMNumApuntes@12349, FMimprimir@12353, FMleeCuenta@12382, FMApunte@12420, FMnuevoRegistro@12460, FMValor@12480, FMVariable@12500

### class CierreContable  (21 métodos, 1041 líneas)

init@19401, PideFechas@19407, AcumulaDatosDiario@19422, AsientoCierre@19473, CreaNuevaEmpresa@19543, GuardaVencimientos@19568, AbreOtraEmpresa@19590, GuardaLbiTmp@19613, LeeLbiTmp@19671, AANNuevo@19722, GuardaCuentas@19778, PonFechas@19986, AANRehacerVtos@19994, AANRehacer@20037, GuardaInventario@20130, LeeInventario@20152, CambioPGCNueva@20235, AsientoAperturaMisma@20304, CambioPGCOtra@20367, AsientoAperturaOtra@21033, ControlIngresosGastosCero@21199

### class ImprimirDiario  (14 métodos, 1038 líneas)

imprimir@16527, ImpNuevoRegistro@16613, init@16964, DiarioTxtDoc@16975, DRAsientoARZ@17003, DRFuncion@17097, DRGenera@17165, DRNuevoRegistro@17249, DiarioResumen@17300, FR_DIARIORESUMEN@17454, FR_DIARIO@17538, ImpFuncionSinC@17713, ImpFuncionConC@17768, DameImporte@17840

### class vUnApunte : JDDW  (25 métodos, 1034 líneas)

Init@9135, Setup2@9377, _Nuevo@9508, _GrabaDatos@9535, EscribeLV@9597, Mas@9641, Abajo@9685, Arriba@9710, BloqueMenos@9736, BloqueMas@9748, Menos@9762, LeeOperacion@9790, LeeConcepto@9810, jLeeBuscar@9819, Multi@9836, _Array2Form@9872, Cambiar@9921, ListViewMouseButtonDoubleClick@9947, LeeContenido@10016, Saldo@10073, RepOpTipo@10116, CambioOperacion@10119, PostInit@10145, TiposAsientos@10151, PonTiposAsientos@10205

### class vDiario : xDLV  (18 métodos, 799 líneas)

Borra@10258, Busca@10301, Edita@10446, Imprime@10454, Otros@10469, columna@10624, GridPreguntaColor@10676, BotonDerecho@10704, Modifica@10707, LanzaMenuNuevo@10840, GridPonValor@10863, GridSiEditamos@10906, BorraAsientos@10913, BorraAsientoActual@10939, Importar@10988, setup2@11008, DameImporte@11013, RenumerarHastaFinal@11031

### class vInfImpGeneral : DATAWINDOW  (21 métodos, 791 líneas)

_GrabaDatos@13843, ListViewMouseButtonDoubleClick@13921, EditFocusChange@13930, BaseActualiza@14345, Init@14691, Cambiar@14772, ControlErrores@14795, EscribeLV@14820, NoImprimir@14911, PeriodosContablesTodas@14926, Setup2@14965, Empresas@15458, CabeceraColumna@15630, DobleClick@15712, CambiarFecha@15747, CambiarTexto@15806, PostInit@15834, CambiaSN@16430, CadSN@16434, Tipos@16437, MoverPeriodos@16495

### class vEInformes : JDDW  (20 métodos, 784 líneas)

Init@7036, Mas@7171, Arriba@7185, Abajo@7211, Menos@7234, _DBF2Variables@7303, EscribeLV@7391, Cambiar@7468, _Nuevo@7552, _GrabaDatos@7821, ControlErrores@7901, ListViewMouseButtonDoubleClick@7923, Tools@7930, Dividir@7996, PostInit@8827, CambiaPGC@8845, Comprobar@8853, PonPGC@8867, PonCuentas@8874, Programa@8923

### class vInformes : jDLVRed  (13 métodos, 674 líneas)

Edita@7490, Borra@7513, CopiaInforme@8091, Otros@8155, Busca@8215, Fusionar@8244, FusionarVerClaves@8317, FusionarAbrirModelo@8331, columna@8880, LeerOtroPGC@8888, PonPGC@8895, Imprime@8962, GridDobleClick@8980

### class vNMayor : vDiario  (15 métodos, 652 líneas)

columna@18202, LaPrimeraVez@18240, MiraCuenta@18249, PonCaption@18264, MiraDesdeHasta@18279, RecalculaSaldo@18293, Otros@18333, Imprime@18357, ImpNuevoRegistro@18375, Edita@18392, ImpFuncion@18416, FR_XCMAYOR@18475, Busca@18688, IniciaFiltro@18801, MueveCuenta@18816

### class vImprimirDiario : JDDW  (10 métodos, 561 líneas)

Init@16738, ControlErrores@16803, Setup2@16836, _GrabaDatos@16884, Tools@16952, DiarioResumen@17049, ButtonClick@17079, DRRotulosNivel@17434, subeControl@17441, PostInit@17859

### class CuentaCorriente  (10 métodos, 536 líneas)

LeerDatos@18854, SaldoCuenta@18945, SaldoInicial@18968, ImpNuevoRegistro@18981, Imprimir@19003, PedirConfiguracion@19032, init@19072, ImpFuncion@19078, FR_@19154, ImpSaldoInicial@19353

### class vCambioGlobalCuentas : JDDW  (15 métodos, 494 líneas)

Mas@304, Menos@352, Init@414, Setup2@461, EscribeLV@471, jLeeBuscar@488, CambiaCuentas@502, Cambiar@556, Tools@574, _GrabaDatos@607, MasGrupo@679, CambiaUna@740, CambiaDBF@759, CambiaContactos@785, PostInit@822

### class vCierre : JDDW  (14 métodos, 436 líneas)

Init@19815, Regularizacion@19856, CierreOtraNueva@19868, CierreOtra@19920, PostInit@19944, MiraPeriodosContables@19966, PonCaptionEmpresa@20126, Tools@20465, CierreMisma@20758, CierreNueva@20781, Fecha@20832, AmortTodos@20864, AmortUno@20909, PlContabiliza@20943

### class CC_Diario : DATAWINDOW  (10 métodos, 429 líneas)

Init@22107, PostInit@22761, DiarioTexto@22866, Busca@22998, Imprime@23060, ImpNuevoRegistro@23149, DiarioDocu@23191, ImpFuncion@23227, FR_CCDIARIO@23284, BotonDerecho@23652

### class CC_Movimientos : DATAWINDOW  (11 métodos, 407 líneas)

Init@22144, PostInit@22583, DiarioTexto@22881, Descripcion@22892, Busca@22954, Imprime@23091, ImpNuevoRegistro@23131, BotonDerecho@23187, DiarioDocu@23203, FR_CCMOVIM@23408, ImpFuncion@23617

### class vInfImpCol : JDDW  (13 métodos, 382 líneas)

Init@14034, Actualiza@14123, ButtonClick@14190, _GrabaDatos@14199, MasEmpresa@14228, Periodo@14237, Mas@14240, Menos@14259, PeriodosContables@14274, Pulsado@14288, Setup2@14334, Tools@14626, PostInit@15828

### class CC_Subcuentas : DATAWINDOW  (9 métodos, 313 líneas)

Init@21901, PostInit@22189, TreeViewSelectionChanging@22241, Busca@22928, Imprime@23076, ImpNuevoRegistro@23103, ImpFuncion@23122, Muestra@23171, FR_CCCUENTAS@23534

### class vEUnaColumna : JDDW  (9 métodos, 310 líneas)

Init@7280, _Array2Variables@7577, _Nuevo@7645, PonContenido@7669, ControlErrores@7703, _GrabaDatos@7754, AlineacionN2C@8069, AlineacionC2N@8080, PostInit@8691

### class vImprimirMayor : JDDW  (8 métodos, 291 líneas)

Init@11267, Setup2@11308, _GrabaDatos@11338, ControlErrores@11361, Tools@11525, PostInit@12232, ImpresionContinua@12291, detFiltro@12297

### class vMayores500 : JDDW  (10 métodos, 259 líneas)

Init@896, _GrabaDatos@965, ControlErrores@980, GridPonValor@2590, Todos@2595, Ninguno@2599, Marca@2602, leeLista@2611, PostInit@3913, Setup2@4533

### class vConsultaContabilidad : JDDW  (6 métodos, 220 líneas)

Init@21857, Tools@22491, TabSelect@22669, PostInit@22848, Buscar@22908, Imprimir@23047

### class ReportIVA  (9 métodos, 213 líneas)

init@4594, cerrar@4601, write@4618, emitida@4621, recibida@4674, repercutido@4727, soportado@4732, iva@4737, terminar@4754

### class IEemitida : _IE  (4 métodos, 211 líneas)

leeBloque@21398, init@21458, graba@21623, grabaIVA@21789

### class vDesdeHastaConsulta : JDDW  (9 métodos, 187 líneas)

Init@22304, Tools@22407, desde@22419, desde@22422, hasta@22425, hasta@22428, ControlErrores@22432, _GrabaDatos@22444, PostInit@22459

### class vEUnaColDatos : DATAWINDOW  (3 métodos, 185 líneas)

Init@8487, ListBoxSelect@8712, PostInit@8833

### class vTipos : DATADIALOG  (9 métodos, 182 líneas)

Grupo@5825, Lista@5829, Linea@5833, Cancelar@5838, Init@5889, PostInit@5958, xControl@6011, TotalGrupo@6097, MenuCommand@6293

### class TZ_Otros : DATAWINDOW  (11 métodos, 166 líneas)

Init@20618, PlBorrar@20687, PlEditar@20697, PlImportar@20708, PlLanzar@20713, PlOrdenar@20730, EscribeLV@20736, PlDuplicar@20740, PlNueva@20752, LeePlantillas@20806, ListViewMouseButtonDoubleClick@20825

### class TZ_Principal : DATAWINDOW  (7 métodos, 162 líneas)

Init@20512, Cierre@20835, AmortTodos@20937, Regularizacion@20940, CierreNueva@21178, CierreOtra@21181, CierreMisma@21196

### class vEActividades : DATAWINDOW  (8 métodos, 146 líneas)

Init@8643, Marcar@8674, Ninguna@8685, Todas@8688, ButtonClick@8729, DameActividades@8745, PonActividades@8764, PostInit@8821

### class vInfImpresion : JDDW  (10 métodos, 144 líneas)

Init@13821, Tools@14420, Setup2@14931, _GrabaDatos@14995, EjecutandoComando@15008, PostInit@15012, Actividades@15647, TabSelect@15651, LaPrimeraVez@16084, Exportar@16089

### class IExt  (6 métodos, 127 líneas)

init@21269, lee@21273, leeBloque@21297, graba@21336, borra@21712, siNuevoCliente@21768

### class vConfigIVA : JDDW  (4 métodos, 125 líneas)

Init@3961, Setup2@4030, ControlErrores@4105, _GrabaDatos@4119

### class _IE  (6 métodos, 106 líneas)

bienClaves@21485, ponClave@21537, ponClaveObligatoria@21541, grabaC@21703, buscaClave@21730, V@21739

### class IEcliente : _IE  (4 métodos, 102 líneas)

leeBloque@21369, init@21434, graba@21544, siCuenta@21785

### class menuApuntes : Menu  (1 métodos, 101 líneas)

Init@5333

### class vInfImpOpciones : DATAWINDOW  (4 métodos, 88 líneas)

Init@15510, _GrabaDatos@15565, Setup2@15579, PostInit@15840

### class vImprimirDMDatos : DATAWINDOW  (3 métodos, 74 líneas)

Init@11624, Periodo@11687, PostInit@12245

### class CCS_Subcuentas : DATAWINDOW  (2 métodos, 73 líneas)

Init@22175, PostInit@22524

### class clPrograma  (4 métodos, 53 líneas)

init@16031, PonAltOpciones@16034, Opcion@16055, CreaPython@16071

### class IEcuenta : _IE  (3 métodos, 34 líneas)

leeBloque@21381, init@21453, graba@21611

### class databrowser  (3 métodos, 23 líneas)

Anchura@10225, AlturaFila@10250, AlturaTitulo@10253

### class BD_DataBrowser : DataBrowser  (1 métodos, 10 líneas)

MouseButtonDown@10240

### class DataColumn  (1 métodos, 8 líneas)

GetWidth@10217

### class _IClave  (1 métodos, 8 líneas)

init@21722

### class fCuentas  (1 métodos, 7 líneas)

SumaDebeHaber@17090

### class ICONCONTROL : Icon  (1 métodos, 5 líneas)

Init@6835

### class ICONGRUPO : Icon  (1 métodos, 5 líneas)

Init@6840

### class ICONINFORME : Icon  (1 métodos, 5 líneas)

Init@6845

### class ICONLINEA : Icon  (1 métodos, 5 líneas)

Init@6850

### class ICONLISTA : Icon  (1 métodos, 5 líneas)

Init@6855

### class ICONTOTAL : Icon  (1 métodos, 3 líneas)

Init@6860

### funciones/procedimientos sueltos (20)

RegulIngresosGastos@1(134), LeePeriodoContable@135(25), OrdenarAsientos@160(85), DiarioDescuadrado@245(37), BorraExtraTipo@282(22), CambioGlobalCuentas@365(49), AdmonLemi@847(49), ControlDeclaracionTerceros@3738(75), AdmonLrec@4140(16), Admon500Proveedores@4156(193), Admon500Clientes@4349(184), EdicionInformes@6863(173), InfLeeOP@9968(48), EdicionDiario@10575(49), InformesRotulo@15592(38), EdicionMayor@18133(69), UnaCuentaCorriente@18934(11), hazCierreContable@20448(17), ImportarExt@21223(46), AConsultarContabilidad@21931(176)

## G_Seguridad  (1783 líneas)


### class CopSeguridad  (19 métodos, 999 líneas)

init@356, Copia@374, Recupera@392, LeeControl@426, ResguardoRapido@528, RecResguardoRapido@583, RecuperaTMP@636, Diaria@649, RecEjemplo@788, Test@801, LeeDiscos@842, RecuperaTMPBase@1004, GuardaUltCopia@1025, CopiasInternas@1067, ResguardoExternoCopia@1458, ResguardoExternoRecupera@1497, CreaZipEmpresaTMP@1531, RecuperaTMPJustificantes@1649, CreaZipEmpresaTMPTraeJustificantes@1706

### class vSeguridad : JDDWsinRed  (8 métodos, 464 líneas)

Init@24, _GrabaDatos@46, Tools@55, CopiaDatos@84, Setup2@271, RecuperaDatos@921, HayImagenes@1450, CompruebaEmpresas@1584

### class vCopInternas : jDLVRed  (13 métodos, 254 líneas)

columna@1177, Edita@1186, CreaNuevo@1194, RecuperaInterno@1229, Borra@1244, GridPonValor@1260, Otros@1287, Recupera@1298, RecuperaExterno@1312, CopiaExterno@1330, RecuperaOtra@1344, GridSiEditamos@1408, Reordenacion@1643

### funciones/procedimientos sueltos (3)

CambiaDestinoCS@1425(25), BorraVersion@1625(6), BorraVersionIndice@1631(12)

## L_General  (5107 líneas)


### class Shell : shellWindow  (130 métodos, 2566 líneas)

Final@1, QueryClose@5, FondoConFoto@36, FondoSinFoto@61, Fondo@79, LeeAplicacionesExternas@170, LeeAplicaciones@302, Bandas@403, PonCaption@744, PonCaptionEmpresa@758, ColorFondo@1651, Accesos@1666, CambioPassword@1675, CopiaSeguridad1Copia@1682, CopiaSeguridad1Recupera@1694, CopiaSeguridadDestino@1712, CopiaSeguridadRecuperaNoEstandar@1718, CopiaSeguridadTest@1721, EditarBase@1731, VideoInicializa@1776, EditarEtiquetas@1781, EjemplosBorrar@1828, Actualizar@1869, CompruebaFDTodo@2003, ReordenarComunes@2121, ReordenaUnComun@2162, ParGen@2181, CopiaSeguridadRecInterna@2190, Calculadora@2206, VersionesAnteriores@2268, ActualizarDatos@2363, CopiaSeguridad@2391, CopiaSeguridadExternaCopia@2412, CopiaSeguridadExternaRecupera@2422, SeguimientoRed@2440, CopiaSeguridadRecupera@2447, AdaptacionPGC@2474, EjemplosLista@2478, EjemplosElegir@2506, EjemplosActivar@2534, siNecesitaActualizar@2622, siNecesitaActualizarDir@2651, ReordenarTodo@2780, ReordenarEmpresas@2825, siNecesitaOrdenarDir@2897, ReordenarModelos@2924, RehacerBase@2955, Avisos@2978, Terminar@2985, ActualizarExtensiones@3014, Clientes@3510, RefEmitidas@3578, Proveedores@3582, IVASoportado@3588, Emitidas@3593, Recibidas@3681, TesoreriaMovimientos@3685, TesoreriaPrevision@3714, ExtrasMovimientos@3718, ExtrasPlantillas@3723, IVARepercutido@3729, Cuentas@3735, OpRecibidas@3739, OpEmitidas@3744, OpClientes@3749, OpProveedores@3754, RefTesoreria@3760, RefClientes@3765, RefProveedores@3770, Parametros@3775, Bancos@3786, Reordenacion@3793, FinEmpresa@3814, RecalculaVencimientos@3825, CompensacionVencimientos@3838, ContaMayorImp@3845, ContaConsulta@3851, ContaRenumerarTodos@3855, ContaRenumerarUno@3862, ContaDiarioCons@3877, RefExtras@3882, AplicacionesExternas@3886, CuentasCambioGlobal@3942, Empresa@3949, ContaAsientosOrdenar@4145, RefRecibidas@4154, EtiquetasEmpresa@4158, ContaCierre@4162, ContaInfComun@4170, ContaInfParticular@4174, Admon500Clientes@4179, Admon500Proveedores@4184, AdmonIVA@4188, ContaAsientosGenerar@4195, ControlDeFicheros@4221, TipoVtos@4241, ControlDeFicherosAut@4246, ControlDeFicherosMan@4251, AdmonLrecG@4255, AdmonLemiG@4259, ContaLbi@4263, AdmonLVentas@4269, AdmonLCompras@4276, ContaInfEstandar@4283, RegTodoFget@4287, AdmonRCompras@4303, AdmonRVentas@4310, RegenerarTodo@4317, ContaMayorCons@4433, ContaDiarioImp@4437, TesoreriaDeBanco@4446, ContaActEdicion@4455, ContaMayorCtaCte@4460, TesoreriaVencimientos@4464, ContaCambioPlanContable@4469, TesoreriaRemesas@4475, XAccess@4480, XSQLite@4489, AdmonLemiFR@4499, AdmonLrecFR@4503, EmpresaElige@4507, Familias@4558, Articulos@4563, AlbEmitidos@4572, AlbRecibidos@4576, Inventarios@4581, Presupuestos@4585, Pedidos@4589, PedidosE@4593, ArtMovimientos@4597

### class shell  (18 métodos, 928 líneas)

Sigue@11, OtraFoto@93, ComprobacionesPrevias@101, Dispatch@365, AyudaMenu@378, LeeOpcionesEmpresa@417, PonMenuOpciones@526, DameRutina@657, Init@667, PonMenuEmpresa@921, ActualizarMGDAhora@2681, ActualizarMGD@2703, ActualizarDia@2735, ActualizarMes@2738, ActualizarSemana@2741, ActualizarNunca@2744, ActualizarCambiar@2748, ActualizarConsultar@2756

### class clActualizar : clLL_Base  (8 métodos, 321 líneas)

Init@4602, LeerURL@4633, Comprueba@4674, CompruebaUno@4705, Grabar@4894, CompruebaBase@4904, Consultar@4932, LeeINS@5017

### class SHELL  (4 métodos, 237 líneas)

MenuCommand@191, Ayuda@253, PonMenuInicio@763, Comando@868

### class AcercaDe : DIALOGWINDOW  (6 métodos, 139 líneas)

Init@1283, Licencia@1356, mail@1360, salir@1367, web@1370, setup@1377

### class vActualizar : DIALOGWINDOW  (5 métodos, 135 líneas)

Init@4773, Setup2@4862, Actualizar@4887, Siguiente@5094, Cancelar@5102

### class vActConsulta : jDLV  (4 métodos, 50 líneas)

GridPonValor@5044, Instalar@5054, Edita@5059, Eliminar@5063

### class AMGD : Icon  (1 métodos, 3 líneas)

Init@1436

### funciones/procedimientos sueltos (17)

Licencia@221(32), lanzaAcercaDe@1422(14), Rellena@1439(37), CentreBitMap@1476(89), MdiClientWinProc@1565(76), SubClassWindow@1641(10), ErroresPrograma@3040(118), MGDCambiaPassword@3158(18), LeeArgError@3176(7), MGDResetPassword@3183(67), ParametrosGenerales@3250(57), loadlib@3307(9), MGDLeePassword@3316(97), AbreVideo@3413(15), EnviaErrores@3428(32), ActCopSeg@3460(46), BorraLanzadera@3506(4)

## mgd0  (11 líneas)


### class App  (1 métodos, 6 líneas)

Start@1

### class AMGD : Icon  (1 métodos, 5 líneas)

Init@7

## mgdDLL  (1199 líneas)


### class App  (3 métodos, 540 líneas)

Start1@1, ALT9@114, Start@196

### class jNuevo_dbf  (3 métodos, 20 líneas)

init@1105, campo@1110, crea@1114

### funciones/procedimientos sueltos (43)

usaEmpresa@180(16), apuXM@557(67), ordenDBF_1@624(5), Zconvierte@629(23), convierteZ@652(33), ordenDBF_R@685(4), ordenDBF_1R@689(6), ordenDBF@695(4), ordenDBF_2@699(5), leeparametro@704(17), ultimoDBF@721(16), recalculasaldos@737(5), N@742(5), xUsaEmpresa@747(17), xInicio@764(50), accessDBF@814(34), cnumeroDBF@848(33), contabilizaDBF@881(19), recuperaDBF@900(4), marcaDBF@904(21), _finfo@925(18), vencimientoProveedor@943(15), vencimientoCliente@958(22), cierraDBF@980(3), xCerrar@983(4), vencimientoAutomatico@987(10), dbf_access@997(21), dbf_inicio@1018(15), dbf_orden@1033(4), dbf_orden_1@1037(5), dbf_orden_1R@1042(6), dbf_orden_2@1048(5), dbf_orden_R@1053(6), dbf_open@1059(6), dbf_close@1065(7), dbf_marca@1072(21), dbf_recupera@1093(12), dbf_open_s@1125(20), dbf_new@1145(8), dbf_pos@1153(17), dbf_newCampo@1170(6), dbf_newCrea@1176(12), dbf_field@1188(12)
