-- =====================================================================
-- Vidro Export Backoffice — schema MySQL 8.0+
-- Execução:  mysql -u root -p < database/mysql/schema.sql
-- Equivalente ao armazenamento JSON (database/schema_def.py).
-- O administrador inicial NÃO é criado aqui (nenhuma senha em texto puro):
-- use  `flask --app app create-admin`  ou a tela /setup no primeiro acesso.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS vidro_export
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE vidro_export;

SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS usuarios (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nome            VARCHAR(120) NOT NULL,
  username        VARCHAR(40)  NOT NULL,
  email           VARCHAR(150) NOT NULL,
  password_hash   VARCHAR(255) NOT NULL,
  perfil          ENUM('admin','operador') NOT NULL DEFAULT 'operador',
  ativo           TINYINT(1)   NOT NULL DEFAULT 1,
  criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_usuarios__username (username),
  UNIQUE KEY uk_usuarios__email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS configuracoes (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
  chave           VARCHAR(60)  NOT NULL,
  valor           VARCHAR(255) NOT NULL,
  atualizado_em   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_configuracoes__chave (chave)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS produtos (
  id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  codigo          VARCHAR(40)   NOT NULL,
  nome            VARCHAR(150)  NOT NULL,
  descricao       TEXT          NULL,
  custo_unitario  DECIMAL(14,4) NOT NULL,
  moeda           CHAR(3)       NOT NULL DEFAULT 'USD',
  estoque         INT UNSIGNED  NOT NULL DEFAULT 0,
  ativo           TINYINT(1)    NOT NULL DEFAULT 1,
  criado_em       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_produtos__codigo (codigo),
  KEY idx_produtos_nome (nome),
  KEY idx_produtos_ativo (ativo),
  CONSTRAINT chk_produtos_custo CHECK (custo_unitario > 0),
  CONSTRAINT chk_produtos_moeda CHECK (CHAR_LENGTH(moeda) = 3)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS clientes (
  id                   INT UNSIGNED NOT NULL AUTO_INCREMENT,
  nome                 VARCHAR(150) NOT NULL,
  pais                 VARCHAR(80)  NOT NULL,
  cidade               VARCHAR(80)  NOT NULL,
  email                VARCHAR(150) NULL,
  telefone             VARCHAR(40)  NULL,
  endereco             VARCHAR(255) NULL,
  identificacao_fiscal VARCHAR(60)  NULL,
  criado_em            DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_clientes_nome (nome),
  KEY idx_clientes_pais (pais)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS pedidos (
  id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  numero          VARCHAR(20)   NULL,
  cliente_id      INT UNSIGNED  NOT NULL,
  moeda           CHAR(3)       NOT NULL,
  status          ENUM('pendente','confirmado','enviado','concluido','cancelado') NOT NULL DEFAULT 'pendente',
  total           DECIMAL(16,2) NOT NULL DEFAULT 0,
  observacoes     TEXT          NULL,
  data_pedido     DATETIME      NOT NULL,
  criado_por      INT UNSIGNED  NULL,
  criado_em       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_pedidos__numero (numero),
  KEY idx_pedidos_status (status),
  KEY idx_pedidos_data (data_pedido),
  KEY idx_pedidos_moeda (moeda),
  CONSTRAINT fk_pedidos_cliente FOREIGN KEY (cliente_id) REFERENCES clientes (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT fk_pedidos_usuario FOREIGN KEY (criado_por) REFERENCES usuarios (id)
    ON UPDATE CASCADE ON DELETE SET NULL,
  CONSTRAINT chk_pedidos_total CHECK (total >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Cada item guarda uma cópia (snapshot) do custo, multiplicador e taxa de
-- câmbio usados na criação do pedido: alterações futuras não afetam pedidos antigos.
CREATE TABLE IF NOT EXISTS itens_pedido (
  id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  pedido_id       INT UNSIGNED  NOT NULL,
  produto_id      INT UNSIGNED  NOT NULL,
  produto_codigo  VARCHAR(40)   NOT NULL,
  produto_nome    VARCHAR(150)  NOT NULL,
  quantidade      INT UNSIGNED  NOT NULL,
  custo_unitario  DECIMAL(14,4) NOT NULL,
  moeda_custo     CHAR(3)       NOT NULL,
  multiplicador   DECIMAL(8,4)  NOT NULL,
  taxa_cambio     DECIMAL(18,8) NOT NULL,
  data_cotacao    DATE          NOT NULL,
  preco_unitario  DECIMAL(16,2) NOT NULL,
  subtotal        DECIMAL(16,2) NOT NULL,
  PRIMARY KEY (id),
  KEY idx_itens_pedido (pedido_id),
  KEY idx_itens_produto (produto_id),
  CONSTRAINT fk_itens_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos (id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_itens_produto FOREIGN KEY (produto_id) REFERENCES produtos (id)
    ON UPDATE CASCADE ON DELETE RESTRICT,
  CONSTRAINT chk_itens_quantidade CHECK (quantidade > 0),
  CONSTRAINT chk_itens_taxa CHECK (taxa_cambio > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS atividades (
  id              INT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id      INT UNSIGNED NULL,
  acao            VARCHAR(30)  NOT NULL,
  entidade        VARCHAR(30)  NOT NULL,
  entidade_id     INT UNSIGNED NULL,
  descricao       VARCHAR(255) NOT NULL,
  criado_em       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_atividades_data (criado_em),
  CONSTRAINT fk_atividades_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
    ON UPDATE CASCADE ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO configuracoes (chave, valor) VALUES
  ('multiplicador_preco', '2'),
  ('moeda_padrao', 'USD'),
  ('empresa_nome', 'Vidro Export');

-- ---------------------------------------------------------------------
-- Usuário de aplicação com privilégios mínimos (recomendado em vez de root).
-- Descomente, troque a senha e execute como administrador do MySQL:
-- CREATE USER IF NOT EXISTS 'vidro_app'@'localhost' IDENTIFIED BY 'troque_esta_senha';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON vidro_export.* TO 'vidro_app'@'localhost';
-- FLUSH PRIVILEGES;
-- ---------------------------------------------------------------------
