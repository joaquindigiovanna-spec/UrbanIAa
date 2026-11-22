/* Validaciones de formularios y confirmaciones (JavaScript puro). */
(function () {
  'use strict';
  var EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  // Confirmación antes de acciones destructivas
  document.querySelectorAll('form[data-confirmar]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      if (!window.confirm(f.getAttribute('data-confirmar'))) { e.preventDefault(); }
    });
  });

  function marcar(campo, malo) { campo.classList.toggle('invalido', !!malo); }
  function mostrarError(msg) {
    var el = document.getElementById('error-form');
    if (el) { el.textContent = msg || ''; }
  }

  var reg = document.getElementById('form-registro');
  if (reg) {
    reg.addEventListener('submit', function (e) {
      var nombre = reg.nombre, email = reg.email, p1 = reg.password, p2 = reg.password2, msg = '';
      marcar(nombre, nombre.value.trim().length < 3);
      marcar(email, !EMAIL.test(email.value.trim()));
      marcar(p1, p1.value.length < 8);
      marcar(p2, p1.value !== p2.value);
      if (nombre.value.trim().length < 3) msg = 'El nombre debe tener al menos 3 caracteres.';
      else if (!EMAIL.test(email.value.trim())) msg = 'Ingrese un correo electrónico válido.';
      else if (p1.value.length < 8) msg = 'La contraseña debe tener al menos 8 caracteres.';
      else if (p1.value !== p2.value) msg = 'Las contraseñas no coinciden.';
      mostrarError(msg);
      if (msg) e.preventDefault();
    });
  }

  var log = document.getElementById('form-login');
  if (log) {
    log.addEventListener('submit', function (e) {
      var vacio = !log.email.value.trim() || !log.password.value;
      marcar(log.email, !log.email.value.trim());
      marcar(log.password, !log.password.value);
      if (vacio) e.preventDefault();
    });
  }
})();
