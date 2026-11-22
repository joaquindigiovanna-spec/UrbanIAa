/* Resumen provincial: ranking de ciudades y totales por cluster. */
(function () {
  'use strict';
  var nodo = document.getElementById('datos-resumen');
  if (!nodo || typeof Chart === 'undefined') return;
  var datos = JSON.parse(nodo.textContent);
  var rank = document.getElementById('graf-ranking'), cl = document.getElementById('graf-clusters');
  if (rank && datos.ciudades.length) {
    var top = datos.ciudades.slice(0, 15);
    rank.setAttribute('aria-label', 'Gráfico de barras horizontales de hectáreas urbanizadas por ciudad. ' +
      top.map(function (c) { return c.ciudad + ': ' + c.ha_urbanizadas + ' ha'; }).join('; '));
    new Chart(rank, {
      type: 'bar',
      data: { labels: top.map(function (c) { return c.ciudad; }),
        datasets: [{ label: 'Nueva urbanización (ha)', data: top.map(function (c) { return c.ha_urbanizadas; }), backgroundColor: '#b4232f', borderColor: '#8f1b25', borderWidth: 1 }] },
      options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } }
    });
  }
  if (cl && datos.clusters.length) {
    cl.setAttribute('aria-label', 'Gráfico de barras por cluster. ' +
      datos.clusters.map(function (c) { return c.cluster + ': ' + c.ha_urbanizadas + ' ha urbanizadas y ' + c.ha_verdes_perdidas + ' ha de vegetación perdida'; }).join('; '));
    new Chart(cl, {
      type: 'bar',
      data: { labels: datos.clusters.map(function (c) { return c.cluster; }),
        datasets: [
          { label: 'Nueva urbanización (ha)', data: datos.clusters.map(function (c) { return c.ha_urbanizadas; }), backgroundColor: '#b4232f', borderColor: '#8f1b25', borderWidth: 1 },
          { label: 'Vegetación perdida (ha)', data: datos.clusters.map(function (c) { return c.ha_verdes_perdidas; }), backgroundColor: '#8bcde8', borderColor: '#147da8', borderWidth: 1 }] },
      options: { scales: { y: { beginAtZero: true } } }
    });
  }
})();
