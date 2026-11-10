/* Conta Pridalac — comportamiento común: tema, listados (orden, columnas, selección, doble clic), diálogo y avisos. */
(function () {
  'use strict';

  // ── Tema: automático → claro → oscuro ───────────────────────────────────────────────────────────────
  var TEMAS = ['auto', 'light', 'dark'];
  var ETIQUETAS = { auto: '◐ Auto', light: '☀ Claro', dark: '🌙 Oscuro' };

  // Las preferencias de pantalla (tema, disposición del menú, última caja) las guarda el programa, no el navegador; la página ya llega con ellas puestas
  var guardarPreferencia = window.guardarPreferencia = function (clave, valor) {
    fetch('/_preferencias', { method: 'POST', headers: { 'X-Conta': 'preferencia', 'Content-Type': 'application/json' }, body: JSON.stringify({ clave: clave, valor: valor }) }).catch(function () { /* vale para esta página */ });
  };

  function temaActual() {
    return document.documentElement.getAttribute('data-theme') || 'auto';
  }
  function aplicarTema(tema, guardar) {
    document.documentElement.setAttribute('data-theme', tema);
    if (guardar) guardarPreferencia('tema', tema);
    var boton = document.getElementById('tema');
    if (boton) { boton.textContent = ETIQUETAS[tema]; boton.setAttribute('data-tema', tema); }
  }
  document.addEventListener('DOMContentLoaded', function () {
    aplicarTema(temaActual(), false);
    var boton = document.getElementById('tema');
    if (boton) boton.addEventListener('click', function () {
      aplicarTema(TEMAS[(TEMAS.indexOf(temaActual()) + 1) % TEMAS.length], true);
    });
  });

  // ── Disposición del menú: opciones debajo de la banda (horizontal) o en una columna a la izquierda (vertical) ─────────────
  var ETIQUETAS_MENU = { horizontal: '☰ Opciones debajo', vertical: '☰ Opciones a la izquierda' };

  function menuActual() {
    return document.documentElement.getAttribute('data-menu') === 'vertical' ? 'vertical' : 'horizontal';
  }
  function aplicarMenu(disposicion, guardar) {
    document.documentElement.setAttribute('data-menu', disposicion);
    if (guardar) guardarPreferencia('menu', disposicion);
    var boton = document.getElementById('disposicion');
    if (boton) boton.textContent = ETIQUETAS_MENU[disposicion];
  }
  document.addEventListener('DOMContentLoaded', function () {
    aplicarMenu(menuActual(), false);
    var boton = document.getElementById('disposicion');
    if (boton) boton.addEventListener('click', function () {
      aplicarMenu(menuActual() === 'vertical' ? 'horizontal' : 'vertical', true);
    });
  });

  // ── Ayudas: las explicaciones de las opciones y de las pantallas, siempre visibles o solo al pasar el ratón ───────────────────
  var ETIQUETAS_AYUDAS = { tooltip: '💬 Ayudas: al pasar', visibles: '💬 Ayudas: fijas' };

  function ayudasActual() {
    return document.documentElement.getAttribute('data-ayudas') === 'visibles' ? 'visibles' : 'tooltip';
  }
  function aplicarAyudas(modo, guardar) {
    document.documentElement.setAttribute('data-ayudas', modo);
    if (guardar) guardarPreferencia('ayudas', modo);
    var boton = document.getElementById('ayudas');
    if (boton) boton.textContent = ETIQUETAS_AYUDAS[modo];
  }
  document.addEventListener('DOMContentLoaded', function () {
    aplicarAyudas(ayudasActual(), false);
    var boton = document.getElementById('ayudas');
    if (boton) boton.addEventListener('click', function () {
      aplicarAyudas(ayudasActual() === 'visibles' ? 'tooltip' : 'visibles', true);
    });
  });

  // ── Diálogo modal ───────────────────────────────────────────────────────────────────────────────────
  function dialogo() { return document.getElementById('modal'); }
  function cerrarModal() {
    var d = dialogo();
    if (d && d.open) d.close();
    var c = document.getElementById('modal-contenido');
    if (c) c.innerHTML = '';
  }
  document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('[data-cerrar-modal]')) cerrarModal();
    var d = dialogo();
    if (d && e.target === d) cerrarModal(); // clic en el fondo
  });
  document.addEventListener('htmx:afterSwap', function (e) {
    if (e.detail.target && e.detail.target.id === 'modal-contenido') {
      var d = dialogo();
      if (d && !d.open && e.detail.target.innerHTML.trim() !== '') {
        d.showModal();
        var primero = d.querySelector('input:not([type=hidden]):not([readonly]), select, textarea');
        if (primero) primero.focus();
      }
    }
  });
  document.addEventListener('cerrarModal', cerrarModal);

  // ── Avisos (toasts) que llegan en la cabecera HX-Trigger ────────────────────────────────────────────
  document.addEventListener('mensaje', function (e) {
    var d = e.detail || {};
    var caja = document.getElementById('avisos');
    if (!caja || !d.texto) return;
    var t = document.createElement('div');
    t.className = 'toast ' + (d.tipo || 'ok');
    t.textContent = d.texto;
    caja.appendChild(t);
    setTimeout(function () { t.remove(); }, d.tipo === 'error' ? 9000 : 3500);
  });

  // Cerrar el programa (el servidor se apaga; para volver a usarlo se abre desde el icono)
  document.addEventListener('click', function (e) {
    if (!(e.target.closest && e.target.closest('#salir'))) return;
    if (!confirm('¿Cerrar el programa? Para volver a usarlo, ábralo desde su icono.')) return;
    fetch('/_apagar', { method: 'POST', headers: { 'X-Conta': 'apagar' } }).then(function (r) {
      if (r.status === 204) document.body.innerHTML = '<main style="padding:3rem;text-align:center"><h1>Programa cerrado</h1><p>Ya puede cerrar esta pestaña. Para volver a usarlo, ábralo desde su icono.</p></main>';
      else avisarError('No se pudo cerrar el programa (' + r.status + '). Ciérrelo desde la ventana donde se ejecuta.');
    }).catch(function () { avisarError('No se puede contactar con el programa.'); });
  });

  // Un error del servidor (500) o de red no debe dejar la pantalla «muerta»: se avisa siempre
  function avisarError(texto) {
    var caja = document.getElementById('avisos');
    if (!caja) return;
    var t = document.createElement('div');
    t.className = 'toast error';
    t.textContent = texto;
    caja.appendChild(t);
    setTimeout(function () { t.remove(); }, 12000);
  }
  document.addEventListener('htmx:responseError', function (e) {
    var estado = e.detail && e.detail.xhr ? e.detail.xhr.status : '';
    if (estado === 401) return;  // la redirección a la contraseña de la empresa ya la gestiona su cabecera
    avisarError('La operación no se ha podido completar (error ' + estado + ' del servidor). Revise la ventana donde se ejecuta el programa.');
  });
  document.addEventListener('htmx:sendError', function () { avisarError('No se puede contactar con el programa: ¿sigue arrancado?'); });

  // ── Listados ────────────────────────────────────────────────────────────────────────────────────────
  function claveAnchos(tabla) { return 'cols:' + tabla.getAttribute('data-lista'); }

  function leerAnchos(tabla) {
    try { return JSON.parse(localStorage.getItem(claveAnchos(tabla)) || '{}'); } catch (e) { return {}; }
  }
  function guardarAnchos(tabla) {
    var anchos = {};
    tabla.querySelectorAll('th[data-clave]').forEach(function (th) { anchos[th.dataset.clave] = th.offsetWidth; });
    try { localStorage.setItem(claveAnchos(tabla), JSON.stringify(anchos)); } catch (e) { /* sin almacenamiento */ }
  }

  /* Reparte el ancho por el peso de cada columna y aplica los anchos que el usuario dejó guardados. */
  function ajustarColumnas(tabla) {
    var cols = Array.prototype.slice.call(tabla.querySelectorAll('th[data-clave]'));
    if (!cols.length) return;
    var guardados = leerAnchos(tabla);
    var total = cols.reduce(function (s, th) { return s + parseFloat(th.dataset.peso || 1); }, 0);
    var disponible = Math.max(tabla.parentElement.clientWidth - (tabla.querySelector('.sel-col') ? 40 : 0), 320);
    var hayGuardados = cols.some(function (th) { return guardados[th.dataset.clave]; });
    var suma = 0;
    cols.forEach(function (th) {
      var ancho = guardados[th.dataset.clave] || Math.max(Math.round(disponible * parseFloat(th.dataset.peso || 1) / total), 84);
      th.style.width = ancho + 'px';
      suma += ancho;
    });
    var sel = tabla.querySelector('th.sel-col');
    if (sel) { sel.style.width = '40px'; suma += 40; }
    tabla.style.width = hayGuardados ? suma + 'px' : '100%';
    if (hayGuardados && suma < tabla.parentElement.clientWidth) tabla.style.width = '100%';
  }

  function actualizarBorrar() {
    var boton = document.getElementById('borrar');
    var acciones = document.querySelectorAll('button.sel-accion');
    if (!boton && !acciones.length) return;
    var marcadas = document.querySelectorAll('.sel:checked').length;
    if (boton) {
      boton.disabled = marcadas === 0;
      boton.textContent = marcadas > 0 ? 'Borrar (' + marcadas + ')' : 'Borrar';
    }
    acciones.forEach(function (b) { b.disabled = marcadas === 0; b.textContent = marcadas > 0 ? b.dataset.texto + ' (' + marcadas + ')' : b.dataset.texto; });
    document.querySelectorAll('.sel').forEach(function (c) { c.closest('tr').classList.toggle('seleccionada', c.checked); });
    var todas = document.getElementById('todas');
    if (todas) {
      var total = document.querySelectorAll('.sel').length;
      todas.checked = total > 0 && marcadas === total;
      todas.indeterminate = marcadas > 0 && marcadas < total;
    }
  }

  document.addEventListener('htmx:afterSettle', function () {
    document.querySelectorAll('table.datos[data-lista]').forEach(ajustarColumnas);
    actualizarBorrar();
  });
  window.addEventListener('resize', function () { document.querySelectorAll('table.datos[data-lista]').forEach(ajustarColumnas); });

  // Ordenar al pulsar la cabecera
  document.addEventListener('click', function (e) {
    var boton = e.target.closest && e.target.closest('th[data-clave] button.orden');
    if (!boton) return;
    var th = boton.closest('th');
    var orden = document.getElementById('orden'), dir = document.getElementById('dir');
    if (!orden) return;
    if (orden.value === th.dataset.clave) dir.value = dir.value === 'asc' ? 'desc' : 'asc';
    else { orden.value = th.dataset.clave; dir.value = 'asc'; }
    htmx.trigger('#tabla', 'refrescar');
  });

  // Selección de filas
  document.addEventListener('change', function (e) {
    if (e.target.id === 'todas') {
      document.querySelectorAll('.sel').forEach(function (c) { c.checked = e.target.checked; });
      actualizarBorrar();
    } else if (e.target.classList && e.target.classList.contains('sel')) {
      actualizarBorrar();
    }
  });

  // Doble clic en una fila: abre su edición (o su detalle si es de sólo lectura)
  document.addEventListener('dblclick', function (e) {
    var fila = e.target.closest && e.target.closest('table.datos[data-doble-clic=si] tbody tr[data-id]');
    if (!fila || e.target.closest('.sel-col')) return;
    var tabla = fila.closest('table');
    htmx.ajax('GET', tabla.dataset.base + '/f/' + encodeURIComponent(fila.dataset.id), { target: '#modal-contenido', swap: 'innerHTML' });
  });
  // Con teclado: Intro sobre una fila enfocada
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && e.target.matches && e.target.matches('table.datos tbody tr[data-id]')) {
      e.target.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    }
    if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      var q = document.getElementById('q');
      if (q) { e.preventDefault(); q.focus(); }
    }
  });

  // Redimensionar columnas arrastrando el borde de la cabecera
  document.addEventListener('mousedown', function (e) {
    var asa = e.target.closest && e.target.closest('.rz');
    if (!asa) return;
    e.preventDefault();
    var th = asa.closest('th'), tabla = th.closest('table');
    var inicioX = e.clientX, inicio = th.offsetWidth;
    // al empezar a arrastrar se fijan en píxeles todos los anchos para que el resto de columnas no se muevan
    var suma = 0;
    tabla.querySelectorAll('th').forEach(function (c) { c.style.width = c.offsetWidth + 'px'; suma += c.offsetWidth; });
    tabla.style.width = suma + 'px';
    asa.classList.add('arrastrando');
    function mover(ev) {
      var nuevo = Math.max(60, inicio + ev.clientX - inicioX);
      th.style.width = nuevo + 'px';
      var total = 0;
      tabla.querySelectorAll('th').forEach(function (c) { total += c.offsetWidth; });
      tabla.style.width = Math.max(total, 0) + 'px';
    }
    function soltar() {
      document.removeEventListener('mousemove', mover);
      document.removeEventListener('mouseup', soltar);
      asa.classList.remove('arrastrando');
      guardarAnchos(tabla);
    }
    document.addEventListener('mousemove', mover);
    document.addEventListener('mouseup', soltar);
  });
  // Doble clic en el borde: ancho automático
  document.addEventListener('dblclick', function (e) {
    var asa = e.target.closest && e.target.closest('.rz');
    if (!asa) return;
    e.stopPropagation();
    var tabla = asa.closest('table');
    try { localStorage.removeItem(claveAnchos(tabla)); } catch (err) { /* nada */ }
    tabla.querySelectorAll('th').forEach(function (c) { c.style.width = ''; });
    ajustarColumnas(tabla);
  }, true);

  // Exportar a PDF o Excel con lo que se ve (búsqueda, parámetros y orden actuales)
  document.addEventListener('click', function (e) {
    var boton = e.target.closest && e.target.closest('[data-exportar]');
    if (!boton) return;
    var form = document.getElementById('filtros');
    var tabla = document.querySelector('table.datos[data-lista]');
    var parametros = new URLSearchParams(new FormData(form));
    parametros.delete('ids');
    if (tabla) { // columnas que el usuario no ve (sin ancho) no existen todavía: se exportan todas las del listado
      parametros.delete('ocultas');
    }
    window.location.href = form.dataset.base + '/exportar.' + boton.dataset.exportar + '?' + parametros.toString();
  });

  // ── Formularios que se recalculan en el servidor: no perder lo que se teclea mientras llega la respuesta ──
  // Al cambiar un campo se envía el formulario y la respuesta sustituye el cuerpo. Si el usuario ya ha seguido escribiendo en
  // otro campo, su texto se conserva (junto con el cursor) en lugar de volver al valor que tenía al enviar.
  var enviado = {};
  document.addEventListener('htmx:beforeRequest', function (e) {
    if (!e.detail.elt || !e.detail.elt.closest || !e.detail.elt.closest('#cuerpo')) return;
    enviado = {};
    document.querySelectorAll('#cuerpo [name]').forEach(function (c) { enviado[c.name] = c.type === 'checkbox' ? c.checked : c.value; });
  });
  document.addEventListener('htmx:beforeSwap', function (e) {
    var destino = e.detail.target;
    if (!destino || destino.id !== 'cuerpo') return;
    var a = document.activeElement;
    destino._enfoque = (a && a.name && destino.contains(a) && enviado[a.name] !== undefined && a.value !== enviado[a.name])
      ? { name: a.name, valor: a.value, ini: a.selectionStart, fin: a.selectionEnd } : null;
    // el desplazamiento del diálogo tampoco se pierde
    destino._scroll = document.getElementById('modal') ? document.getElementById('modal').scrollTop : 0;
  });
  document.addEventListener('htmx:afterSettle', function (e) {
    var cuerpo = document.getElementById('cuerpo');
    var d = e.detail.target;
    if (!cuerpo || !d || d.id !== 'cuerpo') return;
    var modal = document.getElementById('modal');
    if (modal && typeof d._scroll === 'number') modal.scrollTop = d._scroll;
  });
  document.addEventListener('htmx:afterSwap', function (e) {
    // `e.detail.target` es el elemento sustituido (ya fuera del documento): el estado guardado está en él
    var viejo = e.detail.target;
    var f = viejo && viejo._enfoque;
    if (!f) return;
    var nuevo = document.querySelector('#cuerpo [name="' + f.name + '"]');
    if (!nuevo) return;
    nuevo.value = f.valor;
    nuevo.focus();
    try { nuevo.setSelectionRange(f.ini, f.fin); } catch (err) { /* campos sin selección (select, checkbox) */ }
  });
  // ── Buscador de cuentas y terceros ──────────────────────────────────────────────────────────────────
  // Los campos con lista «dl-cuentas…» o «dl-terceros» sugieren mientras se escribe: buscan cada palabra tecleada dentro del número y de
  // la descripción (sin mayúsculas ni tildes). Al elegir se escribe el valor de la opción y se avisa con «change» para que el formulario se recalcule.
  var MAX_SUGERENCIAS = 14;
  var panel = null, campo = null, opciones = [], activa = -1;

  function llevaBuscador(el) {
    return el && el.tagName === 'INPUT' && (el.dataset.lista || /^dl-(cuenta|terceros)/.test(el.getAttribute('list') || ''));
  }
  function normalizar(s) { return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function datosDeLista(el) {
    var lista = document.getElementById(el.dataset.lista);
    if (!lista) return [];
    if (!lista._datos) {
      lista._datos = Array.prototype.map.call(lista.options, function (o) {
        var v = o.value, t = o.textContent || '';
        return { valor: v, texto: t, clave: normalizar(v + ' ' + t) };
      });
    }
    return lista._datos;
  }
  function cerrarPanel() {
    if (panel) { panel.remove(); panel = null; }
    campo = null; opciones = []; activa = -1;
  }
  function pintarActiva() {
    if (!panel) return;
    Array.prototype.forEach.call(panel.children, function (li, i) { li.classList.toggle('activa', i === activa); });
    if (panel.children[activa]) panel.children[activa].scrollIntoView({ block: 'nearest' });
  }
  function elegir(i) {
    var el = campo, o = opciones[i];
    if (!el || !o) return;
    el.value = o.valor;
    cerrarPanel();
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }
  function mostrarSugerencias(el) {
    var palabras = normalizar(el.value).split(/\s+/).filter(Boolean);
    var datos = datosDeLista(el);
    var q = normalizar(el.value).trim();
    var encontrados = datos.filter(function (d) { return palabras.every(function (p) { return d.clave.indexOf(p) >= 0; }); });
    if (q) {  // primero los que empiezan por lo escrito (por el número de cuenta)
      encontrados.sort(function (a, b) { return (a.clave.indexOf(q) === 0 ? 0 : 1) - (b.clave.indexOf(q) === 0 ? 0 : 1); });
    }
    opciones = encontrados.slice(0, MAX_SUGERENCIAS);
    if (!opciones.length) { if (panel) { panel.remove(); panel = null; } activa = -1; campo = el; return; }
    campo = el;
    if (!panel) {
      panel = document.createElement('ul');
      panel.className = 'sugerencias';
      panel.setAttribute('role', 'listbox');
      panel.addEventListener('mousedown', function (ev) {
        ev.preventDefault();  // el campo conserva el foco
        var li = ev.target.closest('li');
        if (li) elegir(Array.prototype.indexOf.call(panel.children, li));
      });
      (el.closest('dialog') || document.body).appendChild(panel);
    }
    panel.innerHTML = '';
    opciones.forEach(function (o) {
      var li = document.createElement('li');
      li.setAttribute('role', 'option');
      if (o.texto) {
        var a = document.createElement('span'); a.className = 'cod'; a.textContent = o.valor;
        var b = document.createElement('span'); b.textContent = o.texto;
        li.appendChild(a); li.appendChild(b);
      } else { li.textContent = o.valor; }
      panel.appendChild(li);
    });
    var r = el.getBoundingClientRect();
    panel.style.left = r.left + 'px';
    panel.style.top = (r.bottom + 2) + 'px';
    panel.style.minWidth = Math.max(r.width, 280) + 'px';
    activa = 0;
    pintarActiva();
  }
  document.addEventListener('focusin', function (e) {
    var el = e.target;
    if (el.tagName === 'INPUT' && !el.dataset.lista && /^dl-(cuenta|terceros)/.test(el.getAttribute('list') || '')) {
      el.dataset.lista = el.getAttribute('list');
      el.removeAttribute('list');  // se sustituye la lista nativa por este buscador
    }
  });
  document.addEventListener('input', function (e) { if (llevaBuscador(e.target) && e.isTrusted) mostrarSugerencias(e.target); });
  document.addEventListener('keydown', function (e) {
    if (!panel || e.target !== campo) return;
    if (e.key === 'ArrowDown') { activa = Math.min(activa + 1, opciones.length - 1); pintarActiva(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { activa = Math.max(activa - 1, 0); pintarActiva(); e.preventDefault(); }
    else if (e.key === 'Enter' && activa >= 0) { e.preventDefault(); elegir(activa); }
    else if (e.key === 'Escape') { cerrarPanel(); e.stopPropagation(); }
  }, true);
  document.addEventListener('focusout', function (e) { if (e.target === campo) cerrarPanel(); });
  document.addEventListener('htmx:beforeSwap', cerrarPanel);
  window.addEventListener('scroll', cerrarPanel, true);
})();

// Avisa al programa de que esta pestaña sigue abierta; si ninguna avisa durante un rato, el programa (arrancado desde el icono) se cierra solo.
(function () {
  function latido() { try { fetch('/_latido', { method: 'POST', keepalive: true }); } catch (e) {} }
  latido();
  setInterval(latido, 15000);
})();

// Banda de cajas del menú: pulsar una pestaña abre sus opciones; pulsarla otra vez, las cierra. En el inicio se vuelve a abrir la última caja que se usó.
(function () {
  var nav = document.querySelector('.cajas');
  if (!nav) return;
  function abrir(id, guardar) {
    nav.querySelectorAll('.caja').forEach(function (c) { c.hidden = c.dataset.caja !== id; });
    nav.querySelectorAll('.pestana').forEach(function (b) {
      var activa = b.dataset.caja === id;
      b.classList.toggle('activa', activa);
      b.setAttribute('aria-expanded', activa ? 'true' : 'false');
    });
    if (guardar) guardarPreferencia('caja', id);
  }
  nav.addEventListener('click', function (e) {
    var b = e.target.closest('.pestana');
    if (b) abrir(b.classList.contains('activa') ? '' : b.dataset.caja, true);
  });
  if (nav.dataset.inicio) {
    var guardada = nav.dataset.guardada;
    if (guardada && nav.querySelector('.pestana[data-caja="' + guardada + '"]')) abrir(guardada, false);
  }
})();
