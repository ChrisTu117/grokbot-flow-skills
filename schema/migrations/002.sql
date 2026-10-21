-- 从 1 到 2：新增 M 表（摩擦）和它的类别枚举；all_codes 视图和 M 的触发器由 ledger.py 按新版 schema.sql 重建
INSERT INTO enum VALUES('M','类别','规矩不顺',1,0);
INSERT INTO enum VALUES('M','类别','被脚本拦',2,0);
INSERT INTO enum VALUES('M','类别','工具报错',3,0);
INSERT INTO enum VALUES('M','类别','用户纠正',4,0);
INSERT INTO enum VALUES('M','类别','返工',5,0);
INSERT INTO enum VALUES('M','类别','其他',6,0);
CREATE TABLE M(
  seq INTEGER PRIMARY KEY CHECK(seq>0),
  code TEXT NOT NULL UNIQUE GENERATED ALWAYS AS ('M-'||seq) VIRTUAL,
  日期 TEXT NOT NULL,
  bot TEXT NOT NULL,
  节号 TEXT NOT NULL,
  类别 TEXT NOT NULL,
  摩擦 TEXT NOT NULL,
  证据 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL
) STRICT;  -- 摩擦：流程用起来不顺的地方，当场记，只增不改不删（schema 2 新增）
