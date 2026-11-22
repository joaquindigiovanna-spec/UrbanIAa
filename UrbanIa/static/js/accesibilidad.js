/* Accesibilidad global: tamaño de texto, alto contraste (se recuerdan en el navegador)
   y lectura en voz alta con la API del navegador (Web Speech). */
(function () {
  'use strict';
  var KF = 'urb_fuente', KC = 'urb_contraste';
  function leerPref(k, def) { try { var v = localStorage.getItem(k); return v === null ? def : v; } catch (e) { return def; } }
  function guardarPref(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* modo privado */ } }
  function $(id) { return document.getElementById(id); }

  var tam = parseInt(leerPref(KF, '100'), 10);
  if (isNaN(tam) || tam < 90 || tam > 160) tam = 100;
  function aplicarTam() { document.documentElement.style.fontSize = tam + '%'; guardarPref(KF, String(tam)); }
  if ($('a11y-menos')) {
    $('a11y-menos').addEventListener('click', function () { tam = Math.max(90, tam - 10); aplicarTam(); });
    $('a11y-mas').addEventListener('click', function () { tam = Math.min(160, tam + 10); aplicarTam(); });
    $('a11y-normal').addEventListener('click', function () { tam = 100; aplicarTam(); });
    var bc = $('a11y-contraste');
    var alto = document.documentElement.getAttribute('data-contraste') === 'alto';
    bc.setAttribute('aria-pressed', alto ? 'true' : 'false');
    bc.addEventListener('click', function () {
      alto = !alto;
      if (alto) document.documentElement.setAttribute('data-contraste', 'alto');
      else document.documentElement.removeAttribute('data-contraste');
      bc.setAttribute('aria-pressed', alto ? 'true' : 'false');
      guardarPref(KC, alto ? '1' : '0');
    });
  }

  /* ---- lectura en voz alta ---- */
  var sintesis = window.speechSynthesis, activo = null;
  function vozDisponible() { return !!(sintesis && window.SpeechSynthesisUtterance); }
  function detener() {
    if (sintesis) sintesis.cancel();
    if (activo) { activo.setAttribute('aria-pressed', 'false'); activo.textContent = activo.dataset.texto; activo = null; }
  }
  function leer(texto, boton) {
    if (!vozDisponible() || !texto) return;
    if (boton && boton === activo) { detener(); return; }
    detener();
    var u = new SpeechSynthesisUtterance(texto);
    u.lang = 'es-AR';
    var v = (sintesis.getVoices() || []).filter(function (x) { return /^es/i.test(x.lang); })[0];
    if (v) u.voice = v;
    u.onend = u.onerror = function () { if (activo === boton) detener(); };
    if (boton) {
      boton.dataset.texto = boton.dataset.texto || boton.textContent;
      boton.setAttribute('aria-pressed', 'true');
      boton.textContent = '⏹ Detener lectura';
      activo = boton;
    }
    sintesis.speak(u);
  }
  window.addEventListener('beforeunload', function () { if (sintesis) sintesis.cancel(); });
  window.UrbaniaA11y = { leer: leer, vozDisponible: vozDisponible };
})();
