/* Visor de resultados con pestañas (panel y detalle comparten el mismo HTML).
   Pestañas: Antes y después | Cambios detectados | Estadísticas | Informe | Fuentes.
   Todo texto proveniente de datos se inserta con textContent (previene XSS). */
var UrbaniaVisor = (function () {
  'use strict';
  var capas = {}, graficos = {}, mapa = null, d = null, resaltado = null, lineaComparacion = null, guiaMapa = null, listo = false;
  var ORDEN = ['tab-antes', 'tab-cambios', 'tab-stats', 'tab-informe', 'tab-fuentes'];
  var COLOR_TIPO = { 'Nueva urbanización': '#D55E00', 'Pérdida de vegetación': '#F0E442', 'Ganancia de vegetación': '#0072B2' };

  function $(id) { return document.getElementById(id); }
  function fmt(n, suf) {
    return (n === null || n === undefined) ? '—' : Number(n).toLocaleString('es-AR', { maximumFractionDigits: 2 }) + (suf || '');
  }
  function el(tag, texto, cls) { var e = document.createElement(tag); if (texto !== undefined) e.textContent = texto; if (cls) e.className = cls; return e; }
  function reducido() { return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
  function anunciar(msg) { var a = $('anuncio'); a.textContent = ''; setTimeout(function () { a.textContent = msg; }, 60); }

  /* ------------------------------------------------------------ mapa base */
  function baseMapas(m) {
    var osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' });
    var sat = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      { maxZoom: 19, attribution: 'Imágenes: Esri, Maxar, Earthstar Geographics' });
    osm.addTo(m);
    L.control.layers({ 'Mapa de calles': osm, 'Vista satelital': sat }).addTo(m);
  }

  function crearGuiaMapa() {
    if (guiaMapa) return;
    guiaMapa = L.control({ position: 'bottomleft' });
    guiaMapa.onAdd = function () {
      var caja = L.DomUtil.create('section', 'guia-mapa');
      caja.setAttribute('aria-label', 'Cómo leer el mapa');
      caja.innerHTML = '<strong class="guia-mapa-titulo">Cómo leer este mapa</strong>' +
        '<p class="guia-mapa-texto"></p>' +
        '<ul class="leyenda-mapa" hidden>' +
        '<li><i class="swatch cambio-urbano"></i>Nueva urbanización</li>' +
        '<li><i class="swatch cambio-verde-urbano"></i>Vegetación convertida a urbano</li>' +
        '<li><i class="swatch cambio-perdida"></i>Vegetación perdida</li>' +
        '<li><i class="swatch cambio-ganancia"></i>Vegetación ganada</li>' +
        '<li><i class="swatch cambio-sin-dato"></i>Sin dato (nubes o sombras)</li>' +
        '</ul><span class="guia-mapa-orientacion" hidden>Norte ↑ arriba · Este → derecha · Oeste ← izquierda</span>';
      L.DomEvent.disableClickPropagation(caja);
      L.DomEvent.disableScrollPropagation(caja);
      return caja;
    };
    guiaMapa.addTo(mapa);
  }

  function actualizarGuiaMapa(modo) {
    if (!guiaMapa || !guiaMapa.getContainer()) return;
    var caja = guiaMapa.getContainer();
    var texto = caja.querySelector('.guia-mapa-texto');
    var leyenda = caja.querySelector('.leyenda-mapa');
    var orientacion = caja.querySelector('.guia-mapa-orientacion');
    if (modo === 'cambios') {
      texto.textContent = 'Imagen ' + d.ano_fin + '. Los colores muestran cambios estimados desde ' + d.ano_inicio + '. El contorno de una zona es aproximado.';
      leyenda.hidden = false;
      orientacion.hidden = false;
      $('mezcla-anios').textContent = 'Vista de cambios: se muestra la imagen ' + d.ano_fin + ' con los cambios estimados desde ' + d.ano_inicio + '.';
      return;
    }
    var mezcla = Number($('cruce').value);
    texto.textContent = 'A la izquierda del separador se ve el año ' + d.ano_inicio +
      '; a la derecha, el año ' + d.ano_fin + '. El año final ocupa ' + mezcla + '% del ancho.';
    var superponer = $('ver-cambio').checked;
    if (superponer) texto.textContent += ' También se superponen los cambios detectados.';
    leyenda.hidden = !superponer;
    orientacion.hidden = true;
    $('mezcla-anios').textContent = 'Izquierda: ' + d.ano_inicio + ' · Derecha: ' + d.ano_fin +
      ' · El año final ocupa ' + mezcla + '% del ancho.';
    $('cruce').setAttribute('aria-valuetext', 'El año ' + d.ano_inicio + ' se ve a la izquierda y el año ' +
      d.ano_fin + ' a la derecha. El año final ocupa ' + mezcla + ' por ciento del ancho.');
  }

  function limpiarCapas() {
    Object.keys(capas).forEach(function (k) { if (mapa && mapa.hasLayer(capas[k])) mapa.removeLayer(capas[k]); });
    capas = {};
    if (resaltado && mapa) { mapa.removeLayer(resaltado); }
    if (lineaComparacion && mapa) { mapa.removeLayer(lineaComparacion); }
    resaltado = null;
    lineaComparacion = null;
  }

  function actualizarComparacion() {
    if (!capas.ini || !capas.fin) return;
    var valor = Number($('cruce').value);
    capas.fin.setOpacity(1);
    capas.fin.getElement().style.clipPath = 'inset(0 0 0 ' + (100 - valor) + '%)';
    var sur = d.bounds[0][0], oeste = d.bounds[0][1], norte = d.bounds[1][0], este = d.bounds[1][1];
    var longitud = oeste + (este - oeste) * valor / 100;
    var puntos = [[sur, longitud], [norte, longitud]];
    if (!lineaComparacion) {
      lineaComparacion = L.polyline(puntos, {
        color: '#b4232f', weight: 4, dashArray: '7 5', interactive: false
      }).addTo(mapa);
    } else {
      lineaComparacion.setLatLngs(puntos);
      if (!mapa.hasLayer(lineaComparacion)) lineaComparacion.addTo(mapa);
    }
    lineaComparacion.bringToFront();
  }

  function modoMapa(modo) {
    if (!capas.ini) return;
    if (modo === 'cambios') {
      capas.ini.setOpacity(0); capas.fin.setOpacity(1); capas.fin.getElement().style.clipPath = 'none';
      capas.cambio.setOpacity(1);
      if (lineaComparacion && mapa.hasLayer(lineaComparacion)) mapa.removeLayer(lineaComparacion);
    }
    else {
      capas.ini.setOpacity(1);
      capas.cambio.setOpacity($('ver-cambio').checked ? 1 : 0);
      actualizarComparacion();
    }
    actualizarGuiaMapa(modo);
  }

  function montarCapas() {
    limpiarCapas();
    crearGuiaMapa();
    var url = function (t) { return '/analisis/' + d.id + '/imagen/' + t + '.png'; };
    capas.ini = L.imageOverlay(url('rgb_inicio'), d.bounds, { opacity: 1, zIndex: 10, interactive: false, alt: 'Imagen satelital ' + d.ano_inicio });
    capas.fin = L.imageOverlay(url('rgb_fin'), d.bounds, { opacity: 1, zIndex: 11, interactive: false, alt: 'Imagen satelital ' + d.ano_fin });
    capas.cambio = L.imageOverlay(url('cambio'), d.bounds, { opacity: 0, zIndex: 12, interactive: false, alt: 'Capa de cambios' });
    capas.ini.addTo(mapa); capas.fin.addTo(mapa); capas.cambio.addTo(mapa);
    mapa.fitBounds(d.bounds);
    var cruce = $('cruce'), ver = $('ver-cambio');
    cruce.value = 50; ver.checked = false;
    cruce.oninput = function () { modoMapa('antes'); };
    ver.onchange = function () { modoMapa('antes'); };
    $('btn-ver-ini').onclick = function () { cruce.value = 0; modoMapa('antes'); anunciar('Mostrando la imagen del año ' + d.ano_inicio); };
    $('btn-ver-fin').onclick = function () { cruce.value = 100; modoMapa('antes'); anunciar('Mostrando la imagen del año ' + d.ano_fin); };
  }

  /* ------------------------------------------------------------- pestañas */
  function activar(id, enfocar) {
    ORDEN.forEach(function (tid) {
      var t = $(tid), p = $(t.getAttribute('aria-controls')), sel = (tid === id);
      t.setAttribute('aria-selected', sel ? 'true' : 'false');
      t.tabIndex = sel ? 0 : -1;
      p.hidden = !sel;
    });
    if (enfocar) $(id).focus();
    if (id === 'tab-antes') modoMapa('antes');
    else if (id === 'tab-cambios') modoMapa('cambios');
    Object.keys(graficos).forEach(function (k) { graficos[k].resize(); });
  }

  function iniciarPestanas() {
    if (listo) return; listo = true;
    ORDEN.forEach(function (id) {
      var t = $(id);
      t.addEventListener('click', function () { activar(id, false); });
      t.addEventListener('keydown', function (e) {
        var vis = ORDEN.filter(function (x) { return !$(x).hidden; }), i = vis.indexOf(id), n = null;
        if (e.key === 'ArrowRight') n = vis[(i + 1) % vis.length];
        else if (e.key === 'ArrowLeft') n = vis[(i - 1 + vis.length) % vis.length];
        else if (e.key === 'Home') n = vis[0];
        else if (e.key === 'End') n = vis[vis.length - 1];
        if (n) { e.preventDefault(); activar(n, true); }
      });
    });
    $('filtro-zonas').addEventListener('change', function () { renderZonas(this.value); });
  }

  /* ------------------------------------------------------------ componentes */
  function tablaAlt(contId, cabecera, filas) {
    var c = $(contId); c.textContent = '';
    var t = el('table'), th = el('thead'), tr = el('tr');
    cabecera.forEach(function (h) { var x = el('th', h); x.scope = 'col'; tr.appendChild(x); });
    th.appendChild(tr); t.appendChild(th);
    var tb = el('tbody');
    filas.forEach(function (f) { var r = el('tr'); f.forEach(function (v) { r.appendChild(el('td', v)); }); tb.appendChild(r); });
    t.appendChild(tb); c.appendChild(el('div', undefined, 'tabla-scroll')).appendChild(t);
  }

  function dato(cont, valor, etiqueta) {
    var div = el('div', undefined, 'dato');
    div.appendChild(el('b', valor)); div.appendChild(el('span', etiqueta)); cont.appendChild(div);
  }

  function datoArea(cont, valor, etiqueta) {
    var div = el('div', undefined, 'dato');
    div.appendChild(el('b', fmt(valor, ' ha')));
    div.appendChild(el('span', etiqueta));
    if (valor !== null && valor !== undefined) {
      div.appendChild(el('small', 'Aprox. ' + fmt(Number(valor) * 1.4) + ' canchas de fútbol', 'dato-ayuda'));
    }
    cont.appendChild(div);
  }

  function cifras() {
    var s = d.stats, i = d.indicadores || {}, c1 = $('res-cifras'), c2 = $('res-indicadores');
    c1.textContent = ''; c2.textContent = '';
    datoArea(c1, s.ha_urbanizadas, 'Nueva superficie urbanizada');
    datoArea(c1, s.ha_verdes_perdidas, 'Vegetación perdida');
    datoArea(c1, s.ha_verdes_ganadas, 'Vegetación ganada');
    datoArea(c1, s.ha_verde_a_urbano, 'Vegetación convertida a urbano');
    datoArea(c1, s.ha_urbanas_inicio, 'Superficie urbana en ' + d.ano_inicio);
    datoArea(c1, s.ha_urbanas_fin, 'Superficie urbana en ' + d.ano_fin);
    dato(c1, fmt(s.pct_verde_inicio, ' %') + ' → ' + fmt(s.pct_verde_fin, ' %'), 'Cobertura vegetal');
    dato(c1, fmt(s.pct_pixeles_validos, ' %'), 'Área válida (sin nubes)');
    dato(c2, i.crecimiento_pct === null || i.crecimiento_pct === undefined ? '—' : fmt(i.crecimiento_pct, ' %'), 'Crecimiento de la superficie urbana');
    dato(c2, fmt(i.ha_por_ano, ' ha/año'), 'Ritmo de urbanización');
    dato(c2, i.pct_urbanizado_era_verde === null || i.pct_urbanizado_era_verde === undefined ? '—' : fmt(i.pct_urbanizado_era_verde, ' %'), 'De lo urbanizado, antes era vegetación');
    dato(c2, i.variacion_verde_pp === null || i.variacion_verde_pp === undefined ? '—' : (i.variacion_verde_pp > 0 ? '+' : '') + fmt(i.variacion_verde_pp, ' puntos'), 'Cambio en la cobertura vegetal');
    $('calidad-analisis').textContent = s.pct_pixeles_validos === null || s.pct_pixeles_validos === undefined
      ? 'No hay un porcentaje disponible para este análisis.'
      : 'Se pudo comparar el ' + fmt(s.pct_pixeles_validos, ' %') + ' del área en las dos imágenes. Las zonas con nubes o sombras se excluyeron; los resultados describen el área comparable, no las partes sin datos.';
  }

  function graficosStats() {
    var s = d.stats;
    var etiquetas = ['Urbano inicial', 'Urbano final', 'Nueva urbanización', 'Vegetación perdida', 'Vegetación ganada'];
    var valores = [s.ha_urbanas_inicio, s.ha_urbanas_fin, s.ha_urbanizadas, s.ha_verdes_perdidas, s.ha_verdes_ganadas];
    $('graf-ha').setAttribute('aria-label', 'Gráfico de barras de hectáreas. ' + etiquetas.map(function (e, k) { return e + ': ' + fmt(valores[k]) + ' ha'; }).join('; '));
    tablaAlt('alt-ha', ['Concepto', 'Hectáreas (est.)'], etiquetas.map(function (e, k) { return [e, fmt(valores[k])]; }));
    if (typeof Chart !== 'undefined') {
      graficos.ha = new Chart($('graf-ha'), {
        type: 'bar',
        data: { labels: etiquetas, datasets: [{ label: 'Hectáreas (estimadas)', data: valores, backgroundColor: ['#b9e3f3', '#147da8', '#b4232f', '#d95b63', '#68b9df'], borderColor: '#fff', borderWidth: 1 }] },
        options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });
    }
    var caja = $('caja-anillos');
    if (d.anillos && d.anillos.length) {
      caja.hidden = false;
      var et = d.anillos.map(function (a) { return a.desde_km + ' a ' + a.hasta_km + ' km'; });
      var v1 = d.anillos.map(function (a) { return a.pct_verde_inicio; }), v2 = d.anillos.map(function (a) { return a.pct_verde_fin; });
      $('graf-anillos').setAttribute('aria-label', 'Gráfico de barras de porcentaje de vegetación por distancia al centro. ' + et.map(function (e, k) { return e + ': ' + fmt(v1[k]) + ' % en ' + d.ano_inicio + ' y ' + fmt(v2[k]) + ' % en ' + d.ano_fin; }).join('; '));
      tablaAlt('alt-anillos', ['Distancia al centro', 'Vegetación ' + d.ano_inicio + ' (%)', 'Vegetación ' + d.ano_fin + ' (%)'], et.map(function (e, k) { return [e, fmt(v1[k]), fmt(v2[k])]; }));
      if (typeof Chart !== 'undefined') {
        graficos.anillos = new Chart($('graf-anillos'), {
          type: 'bar',
          data: { labels: et, datasets: [
            { label: d.ano_inicio + ' (%)', data: v1, backgroundColor: '#b9e3f3', borderColor: '#147da8', borderWidth: 1 },
            { label: d.ano_fin + ' (%)', data: v2, backgroundColor: '#b4232f', borderColor: '#8f1b25', borderWidth: 1 }] },
          options: { scales: { y: { beginAtZero: true, max: 100 } } }
        });
      }
    } else { caja.hidden = true; }
  }

  /* ------------------------------------------------------ pestaña de cambios */
  function verEnMapa(p, n) {
    if (!mapa) return;
    if (resaltado) mapa.removeLayer(resaltado);
    resaltado = L.circleMarker([p.lat, p.lng], {
      radius: 10, color: '#b4232f', weight: 3, fillColor: '#b9e3f3', fillOpacity: 1
    }).addTo(mapa);
    var pop = el('div'); pop.appendChild(el('b', 'Punto de referencia aproximado')); pop.appendChild(document.createElement('br'));
    pop.appendChild(document.createTextNode(p.tipo + ' · ' + fmt(p.ha) + ' ha · a ' + fmt(p.dist_km) + ' km del centro, hacia el ' + p.dir_nombre.toLowerCase() + '.'));
    pop.appendChild(document.createElement('br'));
    pop.appendChild(el('span', 'El punto no representa el contorno exacto de la zona.', 'chico'));
    resaltado.bindPopup(pop).openPopup();
    if (reducido()) mapa.setView([p.lat, p.lng], 16); else mapa.flyTo([p.lat, p.lng], 16, { duration: 0.8 });
    mapa.getContainer().scrollIntoView({ block: 'center', behavior: reducido() ? 'auto' : 'smooth' });
    anunciar('Punto de referencia aproximado ' + n + ': ' + p.tipo + ', ' + fmt(p.ha) + ' hectáreas. El punto no representa el contorno exacto de la zona.');
  }

  function renderZonas(filtro) {
    var tb = $('tabla-zonas').querySelector('tbody'); tb.textContent = '';
    var lista = (d.cambios.parcelas || []).filter(function (p) { return !filtro || p.tipo === filtro; })
      .sort(function (a, b) { return b.ha - a.ha; });
    if (!lista.length) {
      var tr0 = el('tr'), td0 = el('td', 'No hay zonas de este tipo mayores a ' + fmt(d.cambios.min_ha) + ' ha.'); td0.colSpan = 6;
      tr0.appendChild(td0); tb.appendChild(tr0); return;
    }
    lista.forEach(function (p, i) {
      var tr = el('tr'), ET = ['N.º', 'Tipo de cambio', 'Superficie (ha)', 'Ubicación', 'Antes era vegetación', ''];
      tr.appendChild(el('td', String(i + 1)));
      var tdT = el('td'); var sw = el('i', undefined, 'muestra'); sw.style.background = COLOR_TIPO[p.tipo] || '#888'; sw.setAttribute('aria-hidden', 'true');
      tdT.appendChild(sw); tdT.appendChild(document.createTextNode(' ' + p.tipo)); tr.appendChild(tdT);
      tr.appendChild(el('td', fmt(p.ha)));
      tr.appendChild(el('td', 'A ' + fmt(p.dist_km) + ' km del centro, hacia el ' + p.dir_nombre.toLowerCase()));
      tr.appendChild(el('td', p.tipo === 'Ganancia de vegetación' ? '—' : fmt(p.pct_ex_verde, ' %')));
      var tdA = el('td'), b = el('button', 'Ver punto aproximado', 'btn btn-chico btn-zona'); b.type = 'button';
      b.setAttribute('aria-label', 'Ver el punto de referencia aproximado de la zona ' + (i + 1) + ': ' + p.tipo + ', ' + fmt(p.ha) + ' hectáreas. No representa el contorno exacto.');
      b.addEventListener('click', function () { verEnMapa(p, i + 1); });
      tdA.appendChild(b); tr.appendChild(tdA);
      for (var k = 0; k < tr.children.length; k++) tr.children[k].setAttribute('data-et', ET[k]);
      tb.appendChild(tr);
    });
  }

  function pestanaCambios() {
    var tiene = !!(d.cambios && d.cambios.parcelas);
    $('cambios-contenido').hidden = !tiene; $('cambios-vacio').hidden = tiene;
    document.querySelectorAll('.ano-ini').forEach(function (x) { x.textContent = d.ano_inicio; });
    document.querySelectorAll('.ano-fin').forEach(function (x) { x.textContent = d.ano_fin; });
    $('dl-png').href = '/analisis/' + d.id + '/mapa_cambios.png';
    $('dl-png').setAttribute('download', 'mapa_cambios_' + d.ciudad.replace(/\s+/g, '_') + '_' + d.ano_inicio + '_' + d.ano_fin + '.png');
    $('dl-csv').href = '/analisis/' + d.id + '/cambios.csv';
    if (!tiene) return;
    var n = d.cambios.n_zonas || {};
    $('cambios-conteo').textContent = 'Se detectaron ' + (n.urbanizacion || 0) + ' zonas de nueva urbanización, ' +
      (n.perdida_verde || 0) + ' de pérdida de vegetación y ' + (n.ganancia_verde || 0) + ' de ganancia de vegetación ' +
      '(solo se cuentan zonas mayores a ' + fmt(d.cambios.min_ha) + ' ha; se listan las más grandes de cada tipo).';
    $('min-ha').textContent = fmt(d.cambios.min_ha);
    $('filtro-zonas').value = '';
    renderZonas('');
    var dirs = d.cambios.direcciones || [];
    var etiquetas = dirs.map(function (x) { return x.nombre; });
    var urb = dirs.map(function (x) { return x.ha_urbanizadas; }), ver = dirs.map(function (x) { return x.ha_verde_perdido; });
    $('graf-dir').setAttribute('aria-label', 'Gráfico de barras de hectáreas por dirección desde el centro. ' + dirs.map(function (x) { return x.nombre + ': ' + fmt(x.ha_urbanizadas) + ' ha urbanizadas'; }).join('; '));
    tablaAlt('alt-dir', ['Dirección', 'Nueva urbanización (ha)', 'Vegetación perdida (ha)'], dirs.map(function (x) { return [x.nombre, fmt(x.ha_urbanizadas), fmt(x.ha_verde_perdido)]; }));
    if (typeof Chart !== 'undefined') {
      graficos.dir = new Chart($('graf-dir'), {
        type: 'bar',
        data: { labels: etiquetas, datasets: [
          { label: 'Nueva urbanización (ha)', data: urb, backgroundColor: '#D55E00', borderColor: '#333', borderWidth: 1 },
          { label: 'Vegetación perdida (ha)', data: ver, backgroundColor: '#F0E442', borderColor: '#333', borderWidth: 1 }] },
        options: { scales: { y: { beginAtZero: true } } }
      });
    }
  }

  /* ------------------------------------------------- fuentes, informe y voz */
  function escenas() {
    var tb = $('res-escenas').querySelector('tbody'); tb.textContent = '';
    var rot = [d.ano_inicio + ' (inicial)', d.ano_fin + ' (final)'];
    d.escenas.forEach(function (e, i) {
      var tr = el('tr');
      var vals = e && e.id_escena ? [rot[i], e.satelite, e.fecha, fmt(e.nubes, ' %'), e.tile || '—'] : [rot[i], 's/d', 's/d', 's/d', 's/d'];
      vals.forEach(function (v) { tr.appendChild(el('td', v)); });
      var td = el('td');
      if (e && e.url && /^https:\/\//.test(e.url)) {
        var a = el('a', e.producto || 'Ver escena'); a.href = e.url; a.target = '_blank'; a.rel = 'noopener'; td.appendChild(a);
      } else { td.textContent = (e && e.producto) || 'Sin imágenes reales (registro de prueba)'; }
      tr.appendChild(td); tb.appendChild(tr);
    });
  }

  function informe() {
    var r = d.reporte, set = function (id, v) { $(id).textContent = v || '—'; };
    $('bloque-informe').hidden = !r;
    if (!r) return;
    set('txt-diagnostico', r.diagnostico); set('txt-impacto', r.impacto_ambiental);
    set('txt-recomendaciones', r.recomendaciones); set('txt-limitaciones', r.limitaciones);
    $('ins-ia').textContent = r.es_fallback ? 'SIN IA · ' + r.modelo : 'Generado con IA · ' + r.modelo;
  }

  function voz() {
    var ok = window.UrbaniaA11y && window.UrbaniaA11y.vozDisponible();
    $('btn-leer-resumen').hidden = !ok; $('btn-leer-informe').hidden = !ok;
    if (!ok) return;
    $('btn-leer-resumen').onclick = function () { window.UrbaniaA11y.leer($('res-resumen').textContent, this); };
    $('btn-leer-informe').onclick = function () {
      var t = ['Diagnóstico.', $('txt-diagnostico').textContent, 'Impacto ambiental.', $('txt-impacto').textContent,
        'Recomendaciones.', $('txt-recomendaciones').textContent, 'Limitaciones.', $('txt-limitaciones').textContent].join(' ');
      window.UrbaniaA11y.leer(t, this);
    };
  }

  /* ---------------------------------------------------------------- principal */
  function mostrar(m, datos) {
    mapa = m; d = datos;
    Object.keys(graficos).forEach(function (k) { graficos[k].destroy(); }); graficos = {};
    iniciarPestanas();
    $('resultado').hidden = false;
    var tituloMapa = $('mapa-titulo'), descripcionMapa = $('mapa-descripcion');
    if (mapa && d.tiene_imagenes && d.bounds) {
      if (tituloMapa) tituloMapa.textContent = 'Cambios en ' + d.ciudad;
      if (descripcionMapa) descripcionMapa.textContent = 'El mapa se centra en el área analizada. Use las pestañas para comparar los años o ver los cambios detectados.';
      if ($('mapa-cantidad')) $('mapa-cantidad').textContent = 'Área analizada: ' + d.ciudad + ' · ' + d.ano_inicio + ' a ' + d.ano_fin + '.';
    }
    $('res-titulo').textContent = 'Resultados: ' + d.ciudad + ' ' + d.ano_inicio + ' a ' + d.ano_fin + (d.es_demo ? ' (registro de prueba)' : '');
    $('res-resumen').textContent = d.resumen || '';
    $('lbl-ini').textContent = d.ano_inicio; $('lbl-fin').textContent = d.ano_fin;
    $('lbl-ini-b').textContent = d.ano_inicio; $('lbl-fin-b').textContent = d.ano_fin;

    var hayVisor = !!(mapa && d.tiene_imagenes && d.bounds);
    $('tab-antes').hidden = !hayVisor; $('tab-cambios').hidden = !hayVisor;
    if (hayVisor) montarCapas(); else limpiarCapas();
    cifras(); graficosStats(); pestanaCambios(); escenas(); informe(); voz();
    activar(hayVisor ? 'tab-antes' : 'tab-stats', false);
  }

  return { baseMapas: baseMapas, mostrar: mostrar };
})();
