-- Inventory Management System — schema
-- Target: MySQL 8.0+
-- Generated to match app/models.py

CREATE DATABASE IF NOT EXISTS inventory_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE inventory_db;

-- ---------------------------------------------------------------- users
CREATE TABLE IF NOT EXISTS users (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  username       VARCHAR(50)  NOT NULL,
  email          VARCHAR(255) NOT NULL,
  full_name      VARCHAR(120) NOT NULL,
  password_hash  VARCHAR(255) NOT NULL,
  role           VARCHAR(20)  NOT NULL DEFAULT 'clerk',
  is_active      TINYINT(1)   NOT NULL DEFAULT 1,
  last_login_at  DATETIME     NULL,
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_users_username (username),
  UNIQUE KEY uq_users_email    (email),
  CONSTRAINT ck_users_role CHECK (role IN ('admin','manager','clerk'))
) ENGINE=InnoDB;

-- ----------------------------------------------------------- categories
CREATE TABLE IF NOT EXISTS categories (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  name         VARCHAR(80)  NOT NULL,
  description  VARCHAR(500) NULL,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_categories_name (name)
) ENGINE=InnoDB;

-- ------------------------------------------------------------ suppliers
CREATE TABLE IF NOT EXISTS suppliers (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  name            VARCHAR(150) NOT NULL,
  contact_person  VARCHAR(120) NULL,
  phone           VARCHAR(30)  NULL,
  email           VARCHAR(255) NULL,
  address         VARCHAR(500) NULL,
  is_active       TINYINT(1)   NOT NULL DEFAULT 1,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                           ON UPDATE CURRENT_TIMESTAMP,
  KEY ix_suppliers_name (name)
) ENGINE=InnoDB;

-- ------------------------------------------------------------- products
CREATE TABLE IF NOT EXISTS products (
  id                 INT AUTO_INCREMENT PRIMARY KEY,
  sku                VARCHAR(50)  NOT NULL,
  name               VARCHAR(150) NOT NULL,
  description        TEXT         NULL,
  category_id        INT          NULL,
  supplier_id        INT          NULL,
  unit               VARCHAR(20)  NOT NULL DEFAULT 'pcs',
  cost_price         DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  unit_price         DECIMAL(12,2) NOT NULL DEFAULT 0.00,
  quantity_in_stock  INT          NOT NULL DEFAULT 0,
  reorder_level      INT          NOT NULL DEFAULT 10,
  is_active          TINYINT(1)   NOT NULL DEFAULT 1,
  created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_products_sku (sku),
  KEY ix_products_name (name),
  KEY ix_products_active_name (is_active, name),
  KEY ix_products_category (category_id),
  KEY ix_products_supplier (supplier_id),
  CONSTRAINT fk_products_category FOREIGN KEY (category_id)
    REFERENCES categories(id) ON DELETE SET NULL,
  CONSTRAINT fk_products_supplier FOREIGN KEY (supplier_id)
    REFERENCES suppliers(id)  ON DELETE SET NULL,
  CONSTRAINT ck_products_stock_non_negative   CHECK (quantity_in_stock >= 0),
  CONSTRAINT ck_products_reorder_non_negative CHECK (reorder_level >= 0),
  CONSTRAINT ck_products_cost_non_negative    CHECK (cost_price >= 0),
  CONSTRAINT ck_products_price_non_negative   CHECK (unit_price >= 0)
) ENGINE=InnoDB;

-- --------------------------------------------------- stock_transactions
CREATE TABLE IF NOT EXISTS stock_transactions (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  product_id     INT NOT NULL,
  user_id        INT NOT NULL,
  `type`         VARCHAR(20) NOT NULL,
  quantity       INT NOT NULL,
  unit_cost      DECIMAL(12,2) NULL,
  balance_after  INT NOT NULL,
  reference      VARCHAR(100) NULL,
  notes          TEXT NULL,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_txn_product_created (product_id, created_at),
  KEY ix_txn_type_created    (`type`, created_at),
  KEY ix_txn_user (user_id),
  CONSTRAINT fk_txn_product FOREIGN KEY (product_id)
    REFERENCES products(id) ON DELETE CASCADE,
  CONSTRAINT fk_txn_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT ck_txn_quantity_non_negative CHECK (quantity >= 0),
  CONSTRAINT ck_txn_type CHECK (`type` IN ('IN','OUT','ADJUSTMENT'))
) ENGINE=InnoDB;

-- ----------------------------------------------------------- audit_logs
CREATE TABLE IF NOT EXISTS audit_logs (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  user_id     INT NULL,
  action      VARCHAR(50) NOT NULL,
  entity      VARCHAR(50) NOT NULL,
  entity_id   INT NULL,
  details     TEXT NULL,
  ip_address  VARCHAR(45) NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_audit_user_created (user_id, created_at),
  CONSTRAINT fk_audit_user FOREIGN KEY (user_id)
    REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Dedicated application user (least privilege — no DROP, no GRANT)
-- CREATE USER 'ims_user'@'localhost' IDENTIFIED BY 'change-me';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON inventory_db.* TO 'ims_user'@'localhost';
-- FLUSH PRIVILEGES;