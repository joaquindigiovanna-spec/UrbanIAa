-- UrbanIA Córdoba — esquema relacional (MySQL 8 / MariaDB). 8 tablas.
-- Equivale a lo que crea SQLAlchemy con db.create_all(). Los datos iniciales los carga init_db.py.

CREATE TABLE roles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE usuarios (
  id INT AUTO_INCREMENT PRIMARY KEY,
  rol_id INT NOT NULL,
  nombre VARCHAR(100) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  fecha_registro DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (rol_id) REFERENCES roles(id) ON DELETE RESTRICT
);

CREATE TABLE departamentos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL UNIQUE,
  region_geografica VARCHAR(100) NOT NULL
);

CREATE TABLE ciudades (
  id INT AUTO_INCREMENT PRIMARY KEY,
  departamento_id INT NOT NULL,
  nombre VARCHAR(100) NOT NULL,
  cluster VARCHAR(100) NOT NULL,
  latitud DECIMAL(10,7) NOT NULL,
  longitud DECIMAL(10,7) NOT NULL,
  poblacion INT,
  FOREIGN KEY (departamento_id) REFERENCES departamentos(id) ON DELETE RESTRICT
);

CREATE TABLE escenas_satelitales (
  id INT AUTO_INCREMENT PRIMARY KEY,
  satelite VARCHAR(40) NOT NULL,
  producto VARCHAR(150) NOT NULL,
  id_escena VARCHAR(120) NOT NULL UNIQUE,
  fecha_adquisicion DATETIME NOT NULL,
  cobertura_nubes DECIMAL(5,2),
  tile VARCHAR(30),
  url_fuente VARCHAR(500)
);

CREATE TABLE analisis_urbano (
  id INT AUTO_INCREMENT PRIMARY KEY,
  ciudad_id INT NOT NULL,
  usuario_id INT NOT NULL,
  escena_inicio_id INT NULL,
  escena_fin_id INT NULL,
  titulo VARCHAR(150) NOT NULL,
  notas TEXT,
  ano_inicio INT NOT NULL,
  ano_fin INT NOT NULL,
  radio_km INT NOT NULL DEFAULT 3,
  mes_desde INT NOT NULL DEFAULT 5,
  mes_hasta INT NOT NULL DEFAULT 9,
  ha_analizadas DECIMAL(10,2),
  pct_pixeles_validos DECIMAL(5,1),
  ha_urbanas_inicio DECIMAL(10,2),
  ha_urbanas_fin DECIMAL(10,2),
  ha_urbanizadas DECIMAL(10,2) NOT NULL,
  ha_verdes_perdidas DECIMAL(10,2) NOT NULL,
  ha_verdes_ganadas DECIMAL(10,2),
  ha_verde_a_urbano DECIMAL(10,2),
  pct_verde_inicio DECIMAL(5,1),
  pct_verde_fin DECIMAL(5,1),
  anillos_json TEXT,
  cambios_json TEXT,
  bounds_json VARCHAR(200),
  es_demo BOOLEAN NOT NULL DEFAULT FALSE,
  fecha_analisis DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (ciudad_id) REFERENCES ciudades(id) ON DELETE CASCADE,
  FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
  FOREIGN KEY (escena_inicio_id) REFERENCES escenas_satelitales(id) ON DELETE SET NULL,
  FOREIGN KEY (escena_fin_id) REFERENCES escenas_satelitales(id) ON DELETE SET NULL
);

CREATE TABLE imagenes_analisis (
  id INT AUTO_INCREMENT PRIMARY KEY,
  analisis_id INT NOT NULL,
  tipo VARCHAR(20) NOT NULL,           -- rgb_inicio | rgb_fin | cambio
  contenido MEDIUMBLOB NOT NULL,       -- PNG
  UNIQUE KEY uq_imagen_analisis_tipo (analisis_id, tipo),
  FOREIGN KEY (analisis_id) REFERENCES analisis_urbano(id) ON DELETE CASCADE
);

CREATE TABLE reportes_ia (
  id INT AUTO_INCREMENT PRIMARY KEY,
  analisis_id INT NOT NULL UNIQUE,
  diagnostico TEXT NOT NULL,
  impacto_ambiental TEXT NOT NULL,
  recomendaciones TEXT NOT NULL,
  limitaciones TEXT NOT NULL,
  modelo VARCHAR(60) NOT NULL,
  es_fallback BOOLEAN NOT NULL DEFAULT FALSE,
  fecha_generacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (analisis_id) REFERENCES analisis_urbano(id) ON DELETE CASCADE
);
