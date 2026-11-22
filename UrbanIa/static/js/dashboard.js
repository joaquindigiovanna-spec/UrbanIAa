/* Panel principal: mapa de ciudades, filtros por cluster, validación y llamada a la API. */
(function () {
  'use strict';
  var cfg = window.UrbaniaCfg;
  var ciudades = [], marcadores = {};
  var mapa = L.map('mapa').setView([-31.9, -64.2], 7);
  UrbaniaVisor.baseMapas(mapa);

  var selCluster = document.getElementById('f-cluster');
  var selCiudad = document.getElementById('f-ciudad');
  var inBuscar = document.getElementById('f-buscar');
  var form = document.getElementById('form-analisis');
  var err = document.getElementById('error-form');
  var estado = document.getElementById('estado');
  var estadoTxt = document.getElementById('estado-texto');

  function filtradas() {
    var cl = selCluster.value, q = inBuscar.value.trim().toLowerCase();
    return ciudades.filter(function (c) {
      return (!cl || c.cluster === cl) && (!q || c.nombre.toLowerCase().indexOf(q) !== -1);
    });
  }

  function refrescar() {
    var lista = filtradas();
    document.getElementById('mapa-cantidad').textContent = lista.length === 1
      ? 'Se muestra 1 ciudad. Elija otro punto o ajuste los filtros.'
      : 'Se muestran ' + lista.length + ' ciudades. Elija un punto o una ciudad de la lista.';
    selCiudad.textContent = '';
    lista.forEach(function (c) {
      var o = document.createElement('option'); o.value = c.id; o.textContent = c.nombre + ' (' + c.cluster + ')';
      selCiudad.appendChild(o);
    });
    Object.keys(marcadores).forEach(function (id) {
      var visible = lista.some(function (c) { return String(c.id) === id; });
      if (visible) marcadores[id].addTo(mapa); else mapa.removeLayer(marcadores[id]);
    });
    if (lista.length) {
      var b = L.latLngBounds(lista.map(function (c) { return [c.lat, c.lng]; }));
      mapa.fitBounds(b.pad(0.3), { maxZoom: 11 });
    }
  }

  fetch('/api/ciudades').then(function (r) { return r.json(); }).then(function (data) {
    ciudades = data;
    data.forEach(function (c) {
      var m = L.circleMarker([c.lat, c.lng], { radius: 7, color: '#b4232f', fillColor: '#8bcde8', fillOpacity: 0.9 });
      var pop = document.createElement('div');
      var t = document.createElement('b'); t.textContent = c.nombre; pop.appendChild(t);
      pop.appendChild(document.createElement('br'));
      pop.appendChild(document.createTextNode(c.cluster + ' · ' + (c.poblacion ? c.poblacion.toLocaleString('es-AR') + ' hab. (aprox.)' : 's/d')));
      m.bindPopup(pop);
      m.on('click', function () { selCiudad.value = c.id; });
      marcadores[c.id] = m;
    });
    refrescar();
  }).catch(function () {
    err.textContent = 'No se pudieron cargar las ciudades.';
    document.getElementById('mapa-cantidad').textContent = 'No se pudo cargar la lista de ciudades.';
  });

  selCluster.addEventListener('change', refrescar);
  inBuscar.addEventListener('input', refrescar);
  selCiudad.addEventListener('change', function () {
    var c = ciudades.find(function (x) { return String(x.id) === selCiudad.value; });
    if (c) { mapa.flyTo([c.lat, c.lng], 12); if (marcadores[c.id]) marcadores[c.id].openPopup(); }
  });

  function validar() {
    var ai = parseInt(document.getElementById('f-ini').value, 10);
    var af = parseInt(document.getElementById('f-fin').value, 10);
    if (!selCiudad.value) return 'Seleccione una ciudad.';
    if (isNaN(ai) || isNaN(af)) return 'Ingrese los dos años.';
    if (ai < cfg.anioMin || af > cfg.anioMax) return 'Los años deben estar entre ' + cfg.anioMin + ' y ' + cfg.anioMax + '.';
    if (ai >= af) return 'El año inicial debe ser menor que el final.';
    return '';
  }

  var reloj = null;
  function iniciarEstado() {
    var t0 = Date.now(); estado.hidden = false;
    reloj = setInterval(function () {
      var s = Math.round((Date.now() - t0) / 1000);
      estadoTxt.textContent = 'Descargando imágenes Sentinel-2, clasificando y generando informe con IA… ' + s + ' s';
    }, 1000);
    estadoTxt.textContent = 'Consultando el catálogo satelital…';
  }
  function terminarEstado() { clearInterval(reloj); estado.hidden = true; }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!cfg.puedeAnalizar) return;
    var msg = validar(); err.textContent = msg;
    if (msg) return;
    var btn = document.getElementById('btn-analizar'); btn.disabled = true; iniciarEstado();
    document.getElementById('enlace-detalle').hidden = true;

    fetch('/api/analizar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': cfg.csrf },
      body: JSON.stringify({
        ciudad_id: parseInt(selCiudad.value, 10),
        ano_inicio: parseInt(document.getElementById('f-ini').value, 10),
        ano_fin: parseInt(document.getElementById('f-fin').value, 10),
        estacion: document.getElementById('f-estacion').value,
        radio_km: parseInt(document.getElementById('f-radio').value, 10),
        titulo: document.getElementById('f-titulo').value
      })
    }).then(function (r) {
      return r.json().catch(function () { return { error: 'El servidor tardó demasiado o no respondió. Pruebe con un radio menor.' }; })
        .then(function (j) { return { ok: r.ok, datos: j }; });
    }).then(function (res) {
      if (!res.ok) { err.textContent = res.datos.error || 'Error al analizar.'; return; }
      UrbaniaVisor.mostrar(mapa, res.datos);
      var p = document.getElementById('enlace-detalle');
      p.textContent = '';
      var a = document.createElement('a'); a.href = '/analisis/' + res.datos.id; a.textContent = 'Abrir análisis guardado en el historial';
      p.appendChild(a); p.hidden = false;
      document.getElementById('resultado').scrollIntoView({ behavior: 'smooth' });
    }).catch(function () {
      err.textContent = 'No se pudo conectar con el servidor.';
    }).finally(function () { btn.disabled = false; terminarEstado(); });
  });
})();
