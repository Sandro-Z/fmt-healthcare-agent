CREATE DATABASE IF NOT EXISTS wgs_fmt CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE wgs_fmt;

-- SQLAlchemy owns the complete schema. This bootstrap table records that the
-- database is reachable before the API runs Base.metadata.create_all().
CREATE TABLE IF NOT EXISTS infrastructure_bootstrap (
  id INT PRIMARY KEY AUTO_INCREMENT,
  component VARCHAR(80) NOT NULL UNIQUE,
  initialized_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO infrastructure_bootstrap(component) VALUES ('wgs-fmt-backend');
