"""
Crea las tablas y carga datos iniciales. Es idempotente: se puede ejecutar varias veces.
    python init_db.py
"""
import json
import os

from werkzeug.security import generate_password_hash

from app import app
from models import AnalisisUrbano, Ciudad, Departamento, ReporteIA, Rol, Usuario, db

ROLES = ["Administrador", "Planificador Urbano", "Consultor"]

DEPARTAMENTOS = [  # (id, nombre, región)
    (1, "Capital", "Área Metropolitana"), (2, "Colón", "Sierras Chicas / Norte"),
    (3, "Santa María", "Área Metropolitana / Paravachasca"), (4, "Punilla", "Valle de Punilla"),
    (5, "Calamuchita", "Valle de Calamuchita"), (6, "San Javier", "Valle de Traslasierra"),
    (7, "San Alberto", "Valle de Traslasierra"), (8, "Río Cuarto", "Pampa Húmeda"),
    (9, "General San Martín", "Pampa Húmeda"), (10, "San Justo", "Pampa Húmeda"),
    (11, "Tercero Arriba", "Pampa Húmeda"), (12, "Unión", "Pampa Húmeda"),
    (13, "Marcos Juárez", "Pampa Húmeda"), (14, "Presidente Roque Sáenz Peña", "Pampa Húmeda"),
    (15, "Ischilín", "Norte"),
]

# (departamento_id, nombre, cluster, lat, lng, población APROXIMADA: verificar con Censo 2022 INDEC)
CIUDADES = [
    (1, "Córdoba Capital", "Gran Córdoba", -31.4135, -64.1810, 1498060),
    (2, "La Calera", "Gran Córdoba", -31.3462, -64.3364, 45600),
    (2, "Villa Allende", "Gran Córdoba", -31.2947, -64.2957, 36722),
    (3, "Malagueño", "Gran Córdoba", -31.4656, -64.3589, 27000),
    (2, "Unquillo", "Gran Córdoba", -31.2307, -64.3161, 20000),
    (2, "Río Ceballos", "Gran Córdoba", -31.1661, -64.3168, 22400),
    (3, "Alta Gracia", "Gran Córdoba", -31.6529, -64.4283, 60373),
    (4, "Villa Carlos Paz", "Valle de Punilla", -31.4241, -64.4978, 71274),
    (4, "Cosquín", "Valle de Punilla", -31.2444, -64.4658, 26900),
    (5, "Villa General Belgrano", "Valle de Calamuchita", -31.9781, -64.5562, 12000),
    (5, "Santa Rosa de Calamuchita", "Valle de Calamuchita", -32.0697, -64.5367, 15000),
    (6, "Villa Dolores", "Valle de Traslasierra", -31.9458, -65.1883, 31800),
    (7, "Mina Clavero", "Valle de Traslasierra", -31.7225, -65.0028, 10000),
    (8, "Río Cuarto", "Nodos Agroindustriales", -33.1307, -64.3499, 180756),
    (9, "Villa María", "Nodos Agroindustriales", -32.4075, -63.2402, 96061),
    (9, "Villa Nueva", "Nodos Agroindustriales", -32.4333, -63.2500, 21000),
    (10, "San Francisco", "Nodos Agroindustriales", -31.4279, -62.0827, 69047),
    (11, "Río Tercero", "Nodos Agroindustriales", -32.1764, -64.1141, 53166),
    (12, "Bell Ville", "Nodos Agroindustriales", -32.6264, -62.6886, 37610),
    (13, "Marcos Juárez", "Nodos Agroindustriales", -32.6974, -62.1064, 27000),
    (10, "Arroyito", "Nodos Agroindustriales", -31.4206, -63.0503, 25000),
    (14, "Laboulaye", "Nodos Agroindustriales", -34.1264, -63.3911, 21000),
    (2, "Jesús María", "Nodos Regionales Norte", -30.9818, -64.0940, 31602),
    (15, "Deán Funes", "Nodos Regionales Norte", -30.4200, -64.3500, 21500),
]

AVISO_DEMO = ("REGISTRO DE PRUEBA: los valores son ilustrativos y NO provienen del procesamiento de imágenes "
              "reales. Sirven para probar listados, filtros y CRUD. Ejecute un análisis real desde el panel.")

# (ciudad, año ini, año fin, ha_urb, ha_verde_perd, ha_verde_gan, %verde ini, %verde fin, urb ini, urb fin)
DEMOS = [
    ("Córdoba Capital", 2018, 2024, 212.4, 168.9, 31.2, 21.8, 19.6, 1480.0, 1692.4),
    ("Villa Carlos Paz", 2018, 2024, 96.7, 88.1, 12.4, 38.5, 35.9, 410.0, 506.7),
    ("Arroyito", 2018, 2024, 41.3, 38.0, 9.5, 12.2, 11.1, 190.0, 231.3),
    ("Río Cuarto", 2019, 2025, 118.2, 104.6, 20.7, 17.9, 16.3, 820.0, 938.2),
]


def semilla():
    db.create_all()
    if not Rol.query.first():
        db.session.add_all([Rol(nombre=n) for n in ROLES])
        db.session.commit()
    if not Departamento.query.first():
        db.session.add_all([Departamento(id=i, nombre=n, region_geografica=r) for i, n, r in DEPARTAMENTOS])
        db.session.commit()
    if not Ciudad.query.first():
        db.session.add_all([Ciudad(departamento_id=d, nombre=n, cluster=c, latitud=la, longitud=lo, poblacion=p)
                            for d, n, c, la, lo, p in CIUDADES])
        db.session.commit()

    if not Usuario.query.first():
        roles = {r.nombre: r.id for r in Rol.query.all()}
        usuarios = [
            ("Administrador UrbanIA", "admin@urbania.local", "ADMIN_PASSWORD", "Admin1234!", "Administrador"),
            ("Planificador Demo", "planificador@urbania.local", "PLANIFICADOR_PASSWORD", "Plan1234!", "Planificador Urbano"),
            ("Consultor Demo", "consultor@urbania.local", "CONSULTOR_PASSWORD", "Cons1234!", "Consultor"),
        ]
        for nombre, email, var, defecto, rol in usuarios:
            db.session.add(Usuario(rol_id=roles[rol], nombre=nombre, email=email,
                                   password_hash=generate_password_hash(os.getenv(var, defecto))))
        db.session.commit()

    if not AnalisisUrbano.query.filter_by(es_demo=True).first():
        planificador = Usuario.query.filter_by(email="planificador@urbania.local").first()
        for nombre, ai, af, nuevas, perd, gan, pvi, pvf, ui, uf in DEMOS:
            c = Ciudad.query.filter_by(nombre=nombre).first()
            a = AnalisisUrbano(
                ciudad_id=c.id, usuario_id=planificador.id, titulo=f"[PRUEBA] {nombre} {ai}-{af}",
                notas=AVISO_DEMO, ano_inicio=ai, ano_fin=af, radio_km=3, mes_desde=5, mes_hasta=9,
                ha_analizadas=3600.0, pct_pixeles_validos=100.0, ha_urbanas_inicio=ui, ha_urbanas_fin=uf,
                ha_urbanizadas=nuevas, ha_verdes_perdidas=perd, ha_verdes_ganadas=gan,
                ha_verde_a_urbano=round(perd * 0.8, 2), pct_verde_inicio=pvi, pct_verde_fin=pvf,
                anillos_json=json.dumps([]), es_demo=True)
            db.session.add(a)
            db.session.flush()
            db.session.add(ReporteIA(
                analisis_id=a.id, modelo="registro de prueba", es_fallback=True,
                diagnostico=f"[Texto de ejemplo] Se estiman {nuevas} ha de nueva superficie urbanizada en {nombre} "
                            f"entre {ai} y {af}, con una pérdida estimada de {perd} ha de vegetación.",
                impacto_ambiental="[Texto de ejemplo] Mayor impermeabilización y menor infiltración en el período.",
                recomendaciones="1. Verificar en terreno.\n2. Contrastar con cartografía oficial.\n3. Proteger espacios verdes.",
                limitaciones=AVISO_DEMO))
        db.session.commit()


if __name__ == "__main__":
    with app.app_context():
        semilla()
        print(f"Base lista: {Ciudad.query.count()} ciudades, {Usuario.query.count()} usuarios, "
              f"{AnalisisUrbano.query.count()} análisis.")
