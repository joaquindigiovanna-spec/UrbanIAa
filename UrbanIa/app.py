import csv
import io
import json
import re
import secrets
from datetime import datetime
from functools import wraps

from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import analisis as an
import ia
import satelite
from config import Config
from models import (AnalisisUrbano, Ciudad, Departamento, EscenaSatelital,
                    ImagenAnalisis, ReporteIA, Rol, Usuario, db)

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

ROL_ADMIN, ROL_PLANIFICADOR, ROL_CONSULTOR = "Administrador", "Planificador Urbano", "Consultor"
ESTACIONES = {
    "seco": (5, 9, "Mayo a septiembre (estación seca, menos nubes)"),
    "humedo": (1, 4, "Enero a abril (estación húmeda)"),
}
ANIO_MIN = 2017  # primer año con cobertura Sentinel-2 L2A razonable en Argentina
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ============================================================ seguridad / sesión
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


@app.before_request
def antes_de_cada_peticion():
    g.user = None
    uid = session.get("user_id")
    if uid:
        u = db.session.get(Usuario, uid)
        if u and u.activo:
            g.user = u
        else:
            session.pop("user_id", None)
    if request.method == "POST":
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token, session.get("csrf", "")):
            if request.path.startswith("/api/"):
                return jsonify(error="Sesión vencida o petición no válida. Recargue la página."), 400
            abort(400)


@app.context_processor
def inyectar_contexto():
    return {"csrf_token": csrf_token, "usuario": g.get("user"),
            "ROL_ADMIN": ROL_ADMIN, "ROL_PLANIFICADOR": ROL_PLANIFICADOR, "ROL_CONSULTOR": ROL_CONSULTOR}


def login_requerido(f):
    @wraps(f)
    def interna(*a, **kw):
        if not g.user:
            if request.path.startswith("/api/"):
                return jsonify(error="Debe iniciar sesión."), 401
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return interna


def roles_requeridos(*roles):
    def deco(f):
        @wraps(f)
        @login_requerido
        def interna(*a, **kw):
            if g.user.rol.nombre not in roles:
                if request.path.startswith("/api/"):
                    return jsonify(error="Su rol no tiene permiso para esta acción."), 403
                abort(403)
            return f(*a, **kw)
        return interna
    return deco


def puede_modificar(analisis):
    return g.user.rol.nombre == ROL_ADMIN or (
        g.user.rol.nombre == ROL_PLANIFICADOR and analisis.usuario_id == g.user.id)


@app.errorhandler(400)
def e400(_):
    return render_template("error.html", codigo=400, mensaje="Petición no válida o sesión vencida."), 400


@app.errorhandler(403)
def e403(_):
    return render_template("error.html", codigo=403, mensaje="No tiene permiso para acceder a esta sección."), 403


@app.errorhandler(404)
def e404(_):
    return render_template("error.html", codigo=404, mensaje="No encontramos lo que busca."), 404


# ================================================================ autenticación
@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        clave = request.form.get("password", "")
        u = Usuario.query.filter_by(email=email).first()
        if u and u.activo and check_password_hash(u.password_hash, clave):
            session.clear()
            session["user_id"] = u.id
            destino = request.args.get("next", "")
            return redirect(destino if destino.startswith("/") and not destino.startswith("//")
                            else url_for("dashboard"))
        flash("Correo o contraseña incorrectos.", "error")
    return render_template("login.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if g.user:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        email = request.form.get("email", "").strip().lower()
        clave = request.form.get("password", "")
        clave2 = request.form.get("password2", "")
        errores = []
        if len(nombre) < 3 or len(nombre) > 100:
            errores.append("El nombre debe tener entre 3 y 100 caracteres.")
        if not EMAIL_RE.match(email) or len(email) > 120:
            errores.append("Ingrese un correo electrónico válido.")
        if len(clave) < 8:
            errores.append("La contraseña debe tener al menos 8 caracteres.")
        if clave != clave2:
            errores.append("Las contraseñas no coinciden.")
        if not errores and Usuario.query.filter_by(email=email).first():
            errores.append("Ya existe una cuenta con ese correo.")
        if errores:
            for e in errores:
                flash(e, "error")
            return render_template("registro.html", nombre=nombre, email=email)
        rol = Rol.query.filter_by(nombre=ROL_CONSULTOR).first()
        db.session.add(Usuario(rol_id=rol.id, nombre=nombre, email=email,
                               password_hash=generate_password_hash(clave)))
        db.session.commit()
        flash("Cuenta creada. Ya puede iniciar sesión (rol inicial: Consultor).", "ok")
        return redirect(url_for("login"))
    return render_template("registro.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================================================================== páginas
@app.route("/")
def inicio():
    return redirect(url_for("dashboard") if g.user else url_for("login"))


@app.route("/acerca")
def acerca():
    return render_template("acerca.html", umbrales=an.UMBRALES)


@app.route("/dashboard")
@login_requerido
def dashboard():
    clusters = [c[0] for c in db.session.query(Ciudad.cluster).distinct().order_by(Ciudad.cluster)]
    return render_template("dashboard.html", clusters=clusters, estaciones=ESTACIONES,
                           anio_min=ANIO_MIN, anio_max=datetime.now().year,
                           puede_analizar=g.user.rol.nombre in (ROL_ADMIN, ROL_PLANIFICADOR))


@app.get("/api/ciudades")
@login_requerido
def api_ciudades():
    return jsonify([{
        "id": c.id, "nombre": c.nombre, "cluster": c.cluster, "lat": float(c.latitud),
        "lng": float(c.longitud), "poblacion": c.poblacion, "departamento": c.departamento.nombre,
    } for c in Ciudad.query.order_by(Ciudad.cluster, Ciudad.nombre).all()])


# ============================================================ análisis (CRUD)
def _f(v):
    return None if v is None else float(v)


def _stats_de(a):
    return {k: _f(getattr(a, k)) for k in (
        "ha_analizadas", "pct_pixeles_validos", "ha_urbanas_inicio", "ha_urbanas_fin", "ha_urbanizadas",
        "ha_verdes_perdidas", "ha_verdes_ganadas", "ha_verde_a_urbano", "pct_verde_inicio", "pct_verde_fin")}


def _escena_dict(e):
    if not e:
        return {}
    return {"satelite": e.satelite, "producto": e.producto, "id_escena": e.id_escena,
            "fecha": e.fecha_adquisicion.strftime("%d/%m/%Y"), "nubes": _f(e.cobertura_nubes),
            "tile": e.tile, "url": e.url_fuente}


def _tiene_imagenes(a):
    return db.session.query(ImagenAnalisis.id).filter_by(analisis_id=a.id).first() is not None


def analisis_a_dict(a):
    r = a.reporte
    stats = _stats_de(a)
    cambios = json.loads(a.cambios_json) if a.cambios_json else None
    return {
        "id": a.id, "titulo": a.titulo, "ciudad": a.ciudad.nombre, "cluster": a.ciudad.cluster,
        "ano_inicio": a.ano_inicio, "ano_fin": a.ano_fin, "radio_km": a.radio_km,
        "bounds": json.loads(a.bounds_json) if a.bounds_json else None,
        "stats": stats,
        "anillos": json.loads(a.anillos_json) if a.anillos_json else [],
        "cambios": cambios,
        "indicadores": an.indicadores(stats, a.ano_inicio, a.ano_fin),
        "resumen": an.resumen_simple(a.ciudad.nombre, a.ano_inicio, a.ano_fin, stats, cambios),
        "escenas": [_escena_dict(a.escena_inicio), _escena_dict(a.escena_fin)],
        "tiene_imagenes": _tiene_imagenes(a), "es_demo": a.es_demo,
        "reporte": None if not r else {
            "diagnostico": r.diagnostico, "impacto_ambiental": r.impacto_ambiental,
            "recomendaciones": r.recomendaciones, "limitaciones": r.limitaciones,
            "modelo": r.modelo, "es_fallback": r.es_fallback},
    }


def _escenas_para_ia(a):
    def d(e):
        return {"satelite": e.satelite, "fecha": e.fecha_adquisicion.strftime("%d/%m/%Y"),
                "nubes": _f(e.cobertura_nubes)} if e else {"satelite": "s/d", "fecha": "s/d", "nubes": "s/d"}
    return d(a.escena_inicio), d(a.escena_fin)


def _get_o_crear_escena(meta):
    e = EscenaSatelital.query.filter_by(id_escena=meta["id_escena"]).first()
    if not e:
        e = EscenaSatelital(**meta)
        db.session.add(e)
        db.session.flush()
    return e


@app.post("/api/analizar")
@roles_requeridos(ROL_ADMIN, ROL_PLANIFICADOR)
def api_analizar():
    d = request.get_json(silent=True) or {}
    try:
        ciudad_id, ai, af = int(d["ciudad_id"]), int(d["ano_inicio"]), int(d["ano_fin"])
        radio = int(d.get("radio_km", 3))
    except (KeyError, TypeError, ValueError):
        return jsonify(error="Faltan datos o tienen un formato inválido."), 400
    estacion = d.get("estacion", "seco")
    titulo = str(d.get("titulo", "")).strip()[:150]
    if estacion not in ESTACIONES:
        return jsonify(error="Estación no válida."), 400
    if not (ANIO_MIN <= ai < af <= datetime.now().year):
        return jsonify(error=f"Los años deben estar entre {ANIO_MIN} y {datetime.now().year}, y el inicio "
                             f"debe ser menor que el fin."), 400
    if radio not in (2, 3, 4, 5):
        return jsonify(error="El radio debe ser de 2 a 5 km."), 400
    ciudad = db.session.get(Ciudad, ciudad_id)
    if not ciudad:
        return jsonify(error="Ciudad inexistente."), 404

    m1, m2, _ = ESTACIONES[estacion]
    try:
        r = satelite.procesar(float(ciudad.longitud), float(ciudad.latitud), radio, ai, af, m1, m2)
    except satelite.ErrorSatelital as e:
        return jsonify(error=str(e)), 502
    except Exception:
        app.logger.exception("Fallo inesperado procesando imágenes")
        return jsonify(error="Error inesperado al procesar las imágenes. Intente con otro año o radio."), 500

    ea, eb = _get_o_crear_escena(r["escena_inicio"]), _get_o_crear_escena(r["escena_fin"])
    a = AnalisisUrbano(
        ciudad_id=ciudad.id, usuario_id=g.user.id, escena_inicio_id=ea.id, escena_fin_id=eb.id,
        titulo=titulo or f"{ciudad.nombre} {ai}-{af}", ano_inicio=ai, ano_fin=af, radio_km=radio,
        mes_desde=m1, mes_hasta=m2, anillos_json=json.dumps(r["anillos"]),
        cambios_json=json.dumps(r["cambios"]),
        bounds_json=json.dumps(r["bounds"]), es_demo=False, **r["stats"])
    db.session.add(a)
    db.session.flush()
    for tipo, contenido in r["imagenes"].items():
        db.session.add(ImagenAnalisis(analisis_id=a.id, tipo=tipo, contenido=contenido))

    inf = ia.generar_informe(
        {"nombre": ciudad.nombre, "cluster": ciudad.cluster, "poblacion": ciudad.poblacion},
        (ai, af), r["stats"], r["anillos"], _escenas_para_ia(a), r["para_ia"], r["cambios"])
    db.session.add(ReporteIA(analisis_id=a.id, **inf))
    db.session.commit()
    return jsonify(analisis_a_dict(a))


@app.route("/historial")
@login_requerido
def historial():
    q = _filtrar_analisis()
    pagina = request.args.get("pagina", 1, type=int)
    pag = q.paginate(page=pagina, per_page=10, error_out=False)
    clusters = [c[0] for c in db.session.query(Ciudad.cluster).distinct().order_by(Ciudad.cluster)]
    ciudades = Ciudad.query.order_by(Ciudad.nombre).all()
    return render_template("historial.html", pag=pag, clusters=clusters, ciudades=ciudades,
                           filtros={k: v for k, v in request.args.items() if k != "pagina"}, puede_modificar=puede_modificar if g.user else None)


def _filtrar_analisis():
    q = AnalisisUrbano.query.join(Ciudad)
    ciudad_id = request.args.get("ciudad_id", type=int)
    cluster = request.args.get("cluster", "").strip()
    anio = request.args.get("anio", type=int)
    texto = request.args.get("q", "").strip()
    if ciudad_id:
        q = q.filter(AnalisisUrbano.ciudad_id == ciudad_id)
    if cluster:
        q = q.filter(Ciudad.cluster == cluster)
    if anio:
        q = q.filter(AnalisisUrbano.ano_inicio <= anio, AnalisisUrbano.ano_fin >= anio)
    if texto:
        like = f"%{texto}%"
        q = q.filter(db.or_(AnalisisUrbano.titulo.ilike(like), Ciudad.nombre.ilike(like)))
    return q.order_by(AnalisisUrbano.fecha_analisis.desc())


@app.route("/historial.csv")
@login_requerido
def historial_csv():
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["id", "titulo", "ciudad", "cluster", "ano_inicio", "ano_fin", "ha_urbanizadas_estimadas",
                "ha_verdes_perdidas_estimadas", "ha_verdes_ganadas_estimadas", "pct_verde_inicio",
                "pct_verde_fin", "registro_de_prueba", "fecha_analisis"])
    for a in _filtrar_analisis().all():
        w.writerow([a.id, a.titulo, a.ciudad.nombre, a.ciudad.cluster, a.ano_inicio, a.ano_fin,
                    a.ha_urbanizadas, a.ha_verdes_perdidas, a.ha_verdes_ganadas, a.pct_verde_inicio,
                    a.pct_verde_fin, "si" if a.es_demo else "no", a.fecha_analisis.strftime("%Y-%m-%d %H:%M")])
    return Response("\ufeff" + salida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=analisis_urbania.csv"})


@app.route("/analisis/<int:aid>")
@login_requerido
def analisis_detalle(aid):
    a = db.get_or_404(AnalisisUrbano, aid)
    return render_template("analisis.html", a=a, datos=analisis_a_dict(a), puede_modificar=puede_modificar(a))


@app.get("/analisis/<int:aid>/imagen/<tipo>.png")
@login_requerido
def analisis_imagen(aid, tipo):
    if tipo not in ("rgb_inicio", "rgb_fin", "cambio"):
        abort(404)
    img = ImagenAnalisis.query.filter_by(analisis_id=aid, tipo=tipo).first_or_404()
    return Response(img.contenido, mimetype="image/png", headers={"Cache-Control": "private, max-age=86400"})


@app.get("/analisis/<int:aid>/cambios.csv")
@login_requerido
def analisis_cambios_csv(aid):
    a = db.get_or_404(AnalisisUrbano, aid)
    cambios = json.loads(a.cambios_json) if a.cambios_json else {"parcelas": [], "direcciones": []}
    salida = io.StringIO()
    w = csv.writer(salida)
    w.writerow(["tipo", "hectareas_estimadas", "latitud", "longitud", "direccion_desde_centro",
                "distancia_al_centro_km", "porcentaje_que_era_vegetacion"])
    for p in cambios["parcelas"]:
        w.writerow([p["tipo"], p["ha"], p["lat"], p["lng"], p["dir_nombre"], p["dist_km"], p["pct_ex_verde"]])
    w.writerow([])
    w.writerow(["direccion", "ha_nueva_urbanizacion", "ha_vegetacion_perdida"])
    for d in cambios["direcciones"]:
        w.writerow([d["nombre"], d["ha_urbanizadas"], d["ha_verde_perdido"]])
    nombre = f"cambios_{a.ciudad.nombre.replace(' ', '_')}_{a.ano_inicio}_{a.ano_fin}.csv"
    return Response("\ufeff" + salida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


@app.route("/resumen")
@login_requerido
def resumen():
    """Panorama provincial: último análisis de cada ciudad, ranking y totales por cluster."""
    incluir_demo = request.args.get("demo") == "1"
    q = AnalisisUrbano.query.join(Ciudad)
    if not incluir_demo:
        q = q.filter(AnalisisUrbano.es_demo.is_(False))
    ultimos = {}
    for a in q.order_by(AnalisisUrbano.fecha_analisis.desc()).all():
        ultimos.setdefault(a.ciudad_id, a)  # el más reciente de cada ciudad
    filas = []
    for a in ultimos.values():
        ind = an.indicadores(_stats_de(a), a.ano_inicio, a.ano_fin)
        filas.append({"id": a.id, "ciudad": a.ciudad.nombre, "cluster": a.ciudad.cluster,
                      "periodo": f"{a.ano_inicio}-{a.ano_fin}", "ha_urbanizadas": float(a.ha_urbanizadas),
                      "ha_verdes_perdidas": float(a.ha_verdes_perdidas), "es_demo": a.es_demo,
                      "pct_verde_inicio": _f(a.pct_verde_inicio), "pct_verde_fin": _f(a.pct_verde_fin),
                      "crecimiento_pct": ind["crecimiento_pct"]})
    filas.sort(key=lambda f: f["ha_urbanizadas"], reverse=True)
    por_cluster = {}
    for f in filas:
        c = por_cluster.setdefault(f["cluster"], {"cluster": f["cluster"], "ciudades": 0,
                                                  "ha_urbanizadas": 0.0, "ha_verdes_perdidas": 0.0})
        c["ciudades"] += 1
        c["ha_urbanizadas"] = round(c["ha_urbanizadas"] + f["ha_urbanizadas"], 2)
        c["ha_verdes_perdidas"] = round(c["ha_verdes_perdidas"] + f["ha_verdes_perdidas"], 2)
    datos = {"ciudades": filas, "clusters": sorted(por_cluster.values(), key=lambda c: -c["ha_urbanizadas"])}
    totales = {"ciudades": len(filas), "ha_urbanizadas": round(sum(f["ha_urbanizadas"] for f in filas), 1),
               "ha_verdes_perdidas": round(sum(f["ha_verdes_perdidas"] for f in filas), 1),
               "total_ciudades": Ciudad.query.count()}
    return render_template("resumen.html", datos=datos, totales=totales, incluir_demo=incluir_demo)


@app.get("/analisis/<int:aid>/mapa_cambios.png")
@login_requerido
def analisis_mapa_cambios(aid):
    """Imagen final + capa de cambios en un solo PNG, lista para descargar o insertar en un informe."""
    base = ImagenAnalisis.query.filter_by(analisis_id=aid, tipo="rgb_fin").first_or_404()
    capa = ImagenAnalisis.query.filter_by(analisis_id=aid, tipo="cambio").first_or_404()
    return Response(an.compuesto_png(base.contenido, capa.contenido, lado=1200), mimetype="image/png",
                    headers={"Cache-Control": "private, max-age=86400"})


@app.post("/analisis/<int:aid>/editar")
@roles_requeridos(ROL_ADMIN, ROL_PLANIFICADOR)
def analisis_editar(aid):
    a = db.get_or_404(AnalisisUrbano, aid)
    if not puede_modificar(a):
        abort(403)
    titulo = request.form.get("titulo", "").strip()
    if not 3 <= len(titulo) <= 150:
        flash("El título debe tener entre 3 y 150 caracteres.", "error")
    else:
        a.titulo = titulo
        a.notas = request.form.get("notas", "").strip()[:2000] or None
        db.session.commit()
        flash("Análisis actualizado.", "ok")
    return redirect(url_for("analisis_detalle", aid=aid))


@app.post("/analisis/<int:aid>/eliminar")
@roles_requeridos(ROL_ADMIN, ROL_PLANIFICADOR)
def analisis_eliminar(aid):
    a = db.get_or_404(AnalisisUrbano, aid)
    if not puede_modificar(a):
        abort(403)
    db.session.delete(a)
    db.session.commit()
    flash("Análisis eliminado.", "ok")
    return redirect(url_for("historial"))


@app.post("/analisis/<int:aid>/regenerar")
@roles_requeridos(ROL_ADMIN, ROL_PLANIFICADOR)
def analisis_regenerar(aid):
    a = db.get_or_404(AnalisisUrbano, aid)
    if not puede_modificar(a):
        abort(403)
    imgs = []
    for tipo in ("rgb_inicio", "rgb_fin"):
        i = ImagenAnalisis.query.filter_by(analisis_id=a.id, tipo=tipo).first()
        if i:
            imgs.append(i.contenido)
    inf = ia.generar_informe(
        {"nombre": a.ciudad.nombre, "cluster": a.ciudad.cluster, "poblacion": a.ciudad.poblacion},
        (a.ano_inicio, a.ano_fin), _stats_de(a), json.loads(a.anillos_json or "[]"),
        _escenas_para_ia(a), imgs or None, json.loads(a.cambios_json) if a.cambios_json else None)
    if a.reporte:
        for k, v in inf.items():
            setattr(a.reporte, k, v)
        a.reporte.fecha_generacion = datetime.utcnow()
    else:
        db.session.add(ReporteIA(analisis_id=a.id, **inf))
    db.session.commit()
    flash("Informe regenerado." + (" (sin IA: falta configurar GEMINI_API_KEY)" if inf["es_fallback"] else ""), "ok")
    return redirect(url_for("analisis_detalle", aid=aid))


# ============================================================== administración
@app.route("/admin/usuarios")
@roles_requeridos(ROL_ADMIN)
def admin_usuarios():
    return render_template("admin_usuarios.html", usuarios=Usuario.query.order_by(Usuario.id).all(),
                           roles=Rol.query.order_by(Rol.id).all())


@app.post("/admin/usuarios/<int:uid>/rol")
@roles_requeridos(ROL_ADMIN)
def admin_usuario_rol(uid):
    u = db.get_or_404(Usuario, uid)
    rol = db.session.get(Rol, request.form.get("rol_id", type=int))
    if not rol:
        abort(400)
    if u.id == g.user.id:
        flash("No puede cambiar su propio rol.", "error")
    else:
        u.rol_id = rol.id
        db.session.commit()
        flash(f"Rol de {u.nombre} actualizado a {rol.nombre}.", "ok")
    return redirect(url_for("admin_usuarios"))


@app.post("/admin/usuarios/<int:uid>/activo")
@roles_requeridos(ROL_ADMIN)
def admin_usuario_activo(uid):
    u = db.get_or_404(Usuario, uid)
    if u.id == g.user.id:
        flash("No puede desactivarse a sí mismo.", "error")
    else:
        u.activo = not u.activo
        db.session.commit()
        flash(f"Usuario {'activado' if u.activo else 'desactivado'}.", "ok")
    return redirect(url_for("admin_usuarios"))


@app.post("/admin/usuarios/<int:uid>/eliminar")
@roles_requeridos(ROL_ADMIN)
def admin_usuario_eliminar(uid):
    u = db.get_or_404(Usuario, uid)
    if u.id == g.user.id:
        flash("No puede eliminar su propia cuenta.", "error")
    else:
        db.session.delete(u)  # elimina también sus análisis (cascade)
        db.session.commit()
        flash("Usuario eliminado junto con sus análisis.", "ok")
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/ciudades")
@roles_requeridos(ROL_ADMIN)
def admin_ciudades():
    return render_template("admin_ciudades.html", ciudades=Ciudad.query.order_by(Ciudad.cluster, Ciudad.nombre).all())


@app.route("/admin/ciudades/nueva", methods=["GET", "POST"])
@app.route("/admin/ciudades/<int:cid>/editar", methods=["GET", "POST"])
@roles_requeridos(ROL_ADMIN)
def admin_ciudad_form(cid=None):
    c = db.get_or_404(Ciudad, cid) if cid else None
    if request.method == "POST":
        try:
            nombre = request.form["nombre"].strip()
            cluster = request.form["cluster"].strip()
            depto = int(request.form["departamento_id"])
            lat, lng = float(request.form["latitud"]), float(request.form["longitud"])
            pob = request.form.get("poblacion", type=int)
        except (KeyError, ValueError):
            flash("Complete todos los campos con valores válidos.", "error")
            return redirect(request.url)
        if not nombre or not cluster or not db.session.get(Departamento, depto):
            flash("Nombre, cluster y departamento son obligatorios.", "error")
        elif not (-35.5 <= lat <= -29.0 and -66.5 <= lng <= -61.5):
            flash("Las coordenadas están fuera de la Provincia de Córdoba.", "error")
        else:
            if not c:
                c = Ciudad()
                db.session.add(c)
            c.nombre, c.cluster, c.departamento_id = nombre, cluster, depto
            c.latitud, c.longitud, c.poblacion = lat, lng, pob
            db.session.commit()
            flash("Ciudad guardada.", "ok")
            return redirect(url_for("admin_ciudades"))
    return render_template("admin_ciudad_form.html", c=c, departamentos=Departamento.query.order_by(Departamento.nombre).all())


@app.post("/admin/ciudades/<int:cid>/eliminar")
@roles_requeridos(ROL_ADMIN)
def admin_ciudad_eliminar(cid):
    c = db.get_or_404(Ciudad, cid)
    db.session.delete(c)  # también elimina sus análisis
    db.session.commit()
    flash("Ciudad eliminada junto con sus análisis.", "ok")
    return redirect(url_for("admin_ciudades"))


if __name__ == "__main__":
    app.run(debug=True)
