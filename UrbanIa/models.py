from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import deferred

db = SQLAlchemy()


def ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Rol(db.Model):
    __tablename__ = "roles"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)


class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    rol_id = db.Column(db.Integer, db.ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_registro = db.Column(db.DateTime, nullable=False, default=ahora)

    rol = db.relationship("Rol")
    analisis = db.relationship("AnalisisUrbano", backref="usuario", cascade="all, delete-orphan")


class Departamento(db.Model):
    __tablename__ = "departamentos"
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    region_geografica = db.Column(db.String(100), nullable=False)

    ciudades = db.relationship("Ciudad", backref="departamento")


class Ciudad(db.Model):
    __tablename__ = "ciudades"
    id = db.Column(db.Integer, primary_key=True)
    departamento_id = db.Column(db.Integer, db.ForeignKey("departamentos.id", ondelete="RESTRICT"), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    cluster = db.Column(db.String(100), nullable=False)
    latitud = db.Column(db.Numeric(10, 7), nullable=False)
    longitud = db.Column(db.Numeric(10, 7), nullable=False)
    poblacion = db.Column(db.Integer)

    analisis = db.relationship("AnalisisUrbano", backref="ciudad", cascade="all, delete-orphan")


class EscenaSatelital(db.Model):
    """Trazabilidad de cada imagen usada: satélite, fecha, ubicación (tile) y fuente."""
    __tablename__ = "escenas_satelitales"
    id = db.Column(db.Integer, primary_key=True)
    satelite = db.Column(db.String(40), nullable=False)
    producto = db.Column(db.String(150), nullable=False)
    id_escena = db.Column(db.String(120), nullable=False, unique=True)
    fecha_adquisicion = db.Column(db.DateTime, nullable=False)
    cobertura_nubes = db.Column(db.Numeric(5, 2))
    tile = db.Column(db.String(30))
    url_fuente = db.Column(db.String(500))


class AnalisisUrbano(db.Model):
    """Tabla principal del CRUD."""
    __tablename__ = "analisis_urbano"
    id = db.Column(db.Integer, primary_key=True)
    ciudad_id = db.Column(db.Integer, db.ForeignKey("ciudades.id", ondelete="CASCADE"), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    escena_inicio_id = db.Column(db.Integer, db.ForeignKey("escenas_satelitales.id", ondelete="SET NULL"))
    escena_fin_id = db.Column(db.Integer, db.ForeignKey("escenas_satelitales.id", ondelete="SET NULL"))
    titulo = db.Column(db.String(150), nullable=False)
    notas = db.Column(db.Text)
    ano_inicio = db.Column(db.Integer, nullable=False)
    ano_fin = db.Column(db.Integer, nullable=False)
    radio_km = db.Column(db.Integer, nullable=False, default=3)
    mes_desde = db.Column(db.Integer, nullable=False, default=5)
    mes_hasta = db.Column(db.Integer, nullable=False, default=9)
    ha_analizadas = db.Column(db.Numeric(10, 2))
    pct_pixeles_validos = db.Column(db.Numeric(5, 1))
    ha_urbanas_inicio = db.Column(db.Numeric(10, 2))
    ha_urbanas_fin = db.Column(db.Numeric(10, 2))
    ha_urbanizadas = db.Column(db.Numeric(10, 2), nullable=False)
    ha_verdes_perdidas = db.Column(db.Numeric(10, 2), nullable=False)
    ha_verdes_ganadas = db.Column(db.Numeric(10, 2))
    ha_verde_a_urbano = db.Column(db.Numeric(10, 2))
    pct_verde_inicio = db.Column(db.Numeric(5, 1))
    pct_verde_fin = db.Column(db.Numeric(5, 1))
    anillos_json = db.Column(db.Text)
    cambios_json = db.Column(db.Text)  # zonas de cambio y direcciones (ver analisis.detalle_cambios)
    bounds_json = db.Column(db.String(200))
    es_demo = db.Column(db.Boolean, nullable=False, default=False)
    fecha_analisis = db.Column(db.DateTime, nullable=False, default=ahora)

    escena_inicio = db.relationship("EscenaSatelital", foreign_keys=[escena_inicio_id])
    escena_fin = db.relationship("EscenaSatelital", foreign_keys=[escena_fin_id])
    reporte = db.relationship("ReporteIA", backref="analisis", uselist=False, cascade="all, delete-orphan")
    imagenes = db.relationship("ImagenAnalisis", backref="analisis", cascade="all, delete-orphan")


class ImagenAnalisis(db.Model):
    """Mapas PNG generados (se guardan en la BD porque el disco de Render es efímero)."""
    __tablename__ = "imagenes_analisis"
    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(db.Integer, db.ForeignKey("analisis_urbano.id", ondelete="CASCADE"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # rgb_inicio | rgb_fin | cambio
    contenido = deferred(db.Column(db.LargeBinary(length=16777216), nullable=False))

    __table_args__ = (db.UniqueConstraint("analisis_id", "tipo", name="uq_imagen_analisis_tipo"),)


class ReporteIA(db.Model):
    __tablename__ = "reportes_ia"
    id = db.Column(db.Integer, primary_key=True)
    analisis_id = db.Column(db.Integer, db.ForeignKey("analisis_urbano.id", ondelete="CASCADE"),
                            nullable=False, unique=True)
    diagnostico = db.Column(db.Text, nullable=False)
    impacto_ambiental = db.Column(db.Text, nullable=False)
    recomendaciones = db.Column(db.Text, nullable=False)
    limitaciones = db.Column(db.Text, nullable=False)
    modelo = db.Column(db.String(60), nullable=False)
    es_fallback = db.Column(db.Boolean, nullable=False, default=False)
    fecha_generacion = db.Column(db.DateTime, nullable=False, default=ahora)
