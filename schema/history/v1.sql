-- 流程模板台账表结构（随流程模板 v1.0.0 发布）
-- schema_version: 1
-- 一项目一个库：/home/box/flow-data/<项目名>/ledger.db。「流程治理」库另用 B 表（bot 名册）。
-- 只能经 scripts/ledger.py 写入：每个写事务先设 _ctx（写入者、原因、模式），提交前清空；_ctx 为空时所有写入被拒。
-- 连接约定（ledger.py、check.py 都照此）：journal_mode=DELETE；busy_timeout=10000；foreign_keys=ON；写事务一律 BEGIN IMMEDIATE；只读用 mode=ro + query_only。
-- 规则（触发器）是护栏不是权限：DROP TRIGGER 能拆掉，check.py 每次把本库结构与克隆里同版本的 schema 逐条比对。
-- 模式 typo（ledger.py update --typo）：只放开各表的文字核心列（F 内容；D 决定、理由；R 风险、对策；S 结论；P 自验证方式；A 标准、依据、检查方法），只改错字由 ledger.py 核对，修改记录原因以「仅错字」开头。
-- 时间一律 box 本地时间（Asia/Shanghai，北京时间），格式 YYYY-MM-DDTHH:MM:SS。

-- ========== 基础表 ==========
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT) STRICT;
-- 键：schema_version、schema_tag、库ID、库类型（治理/项目）、项目名、项目仓库（仅治理）、流程版本、降级模式、状态（在办/已归档/已回滚）、created_at
CREATE TABLE _ctx(id INTEGER PRIMARY KEY CHECK(id=1), actor TEXT, reason TEXT, mode TEXT CHECK(mode IS NULL OR mode IN ('write','init','migrate','check','backup','typo'))) STRICT;
INSERT INTO _ctx VALUES(1,NULL,NULL,NULL);
CREATE TABLE enum(tbl TEXT NOT NULL, col TEXT NOT NULL, val TEXT NOT NULL, ord INTEGER NOT NULL, 默认隐藏 INTEGER NOT NULL DEFAULT 0 CHECK(默认隐藏 IN (0,1)), PRIMARY KEY(tbl,col,val)) STRICT;
CREATE TABLE f_default_ttl(类别 TEXT PRIMARY KEY, 天数 INTEGER, 写法 TEXT NOT NULL) STRICT;  -- F 每一类的默认有效期（天数为空时按「写法」原样填）

INSERT INTO enum VALUES('F','状态','待查证',1,0);
INSERT INTO enum VALUES('F','状态','已查证',2,0);
INSERT INTO enum VALUES('F','状态','已查证（二手）',3,0);
INSERT INTO enum VALUES('F','状态','已过期',4,0);
INSERT INTO enum VALUES('F','状态','需复查',5,0);
INSERT INTO enum VALUES('F','状态','已推翻',6,1);
INSERT INTO enum VALUES('F','状态','已合并',7,1);
INSERT INTO enum VALUES('F','类别','仓库文件',1,0);
INSERT INTO enum VALUES('F','类别','平台行为',2,0);
INSERT INTO enum VALUES('F','类别','政策规则',3,0);
INSERT INTO enum VALUES('F','类别','外部数据',4,0);
INSERT INTO enum VALUES('F','类别','用户情况',5,0);
INSERT INTO enum VALUES('F','类别','常识定律',6,0);
INSERT INTO enum VALUES('F','类别','其他',7,0);
INSERT INTO enum VALUES('F','登记方式','新增',1,0);
INSERT INTO enum VALUES('F','登记方式','补录',2,0);
INSERT INTO enum VALUES('D','状态','生效',1,0);
INSERT INTO enum VALUES('D','状态','生效（待用户确认）',2,0);
INSERT INTO enum VALUES('D','状态','待定',3,0);
INSERT INTO enum VALUES('D','状态','需复查',4,0);
INSERT INTO enum VALUES('D','状态','作废',5,1);
INSERT INTO enum VALUES('D','状态','已合并',6,1);
INSERT INTO enum VALUES('D','状态','已否决',7,1);
INSERT INTO enum VALUES('D','状态','历史决策',8,0);
INSERT INTO enum VALUES('D','谁拍板','用户',1,0);
INSERT INTO enum VALUES('D','谁拍板','bot',2,0);
INSERT INTO enum VALUES('D','类型','决定',1,0);
INSERT INTO enum VALUES('D','类型','候选',2,0);
INSERT INTO enum VALUES('D','类型','降级',3,0);
INSERT INTO enum VALUES('D','类型','版本',4,0);
INSERT INTO enum VALUES('D','登记方式','新增',1,0);
INSERT INTO enum VALUES('D','登记方式','补录',2,0);
INSERT INTO enum VALUES('R','可能性','高',1,0);
INSERT INTO enum VALUES('R','可能性','中',2,0);
INSERT INTO enum VALUES('R','可能性','低',3,0);
INSERT INTO enum VALUES('R','影响','高',1,0);
INSERT INTO enum VALUES('R','影响','中',2,0);
INSERT INTO enum VALUES('R','影响','低',3,0);
INSERT INTO enum VALUES('R','状态','监控中',1,0);
INSERT INTO enum VALUES('R','状态','已发生',2,0);
INSERT INTO enum VALUES('R','状态','需复查',3,0);
INSERT INTO enum VALUES('R','状态','已消除',4,0);
INSERT INTO enum VALUES('R','状态','已合并',5,1);
INSERT INTO enum VALUES('R','登记方式','新增',1,0);
INSERT INTO enum VALUES('R','登记方式','补录',2,0);
INSERT INTO enum VALUES('S','状态','生效',1,0);
INSERT INTO enum VALUES('S','状态','需复查',2,0);
INSERT INTO enum VALUES('S','状态','作废',3,1);
INSERT INTO enum VALUES('P','状态','未开始',1,0);
INSERT INTO enum VALUES('P','状态','进行中',2,0);
INSERT INTO enum VALUES('P','状态','挂起',3,0);
INSERT INTO enum VALUES('P','状态','自验证中',4,0);
INSERT INTO enum VALUES('P','状态','需复查',5,0);
INSERT INTO enum VALUES('P','状态','已完成',6,0);
INSERT INTO enum VALUES('P','状态','已作废',7,1);
INSERT INTO enum VALUES('P','可逆性','可逆',1,0);
INSERT INTO enum VALUES('P','可逆性','不可逆',2,0);
INSERT INTO enum VALUES('A','级别','必须',1,0);
INSERT INTO enum VALUES('A','级别','可延后',2,0);
INSERT INTO enum VALUES('A','状态','草稿',1,0);
INSERT INTO enum VALUES('A','状态','用户已确认',2,0);
INSERT INTO enum VALUES('A','状态','需复查',3,0);
INSERT INTO enum VALUES('A','状态','已被取代',4,1);
INSERT INTO enum VALUES('A','状态','作废',5,1);
INSERT INTO enum VALUES('B','类型','参谋长',1,0);
INSERT INTO enum VALUES('B','类型','副官',2,0);
INSERT INTO enum VALUES('B','类型','专职',3,0);
INSERT INTO enum VALUES('B','状态','在用',1,0);
INSERT INTO enum VALUES('B','状态','暂停',2,0);
INSERT INTO enum VALUES('B','状态','退役',3,0);
INSERT INTO enum VALUES('B','状态','已废弃',4,1);
INSERT INTO enum VALUES('dep','状态','有效',1,0);
INSERT INTO enum VALUES('dep','状态','作废',2,1);
INSERT INTO f_default_ttl VALUES('仓库文件',NULL,'到本项目仓库下一个 tag 发布');
INSERT INTO f_default_ttl VALUES('平台行为',30,'查证日期起 30 天');
INSERT INTO f_default_ttl VALUES('政策规则',90,'查证日期起 90 天（政策自身写明有效期的以政策为准）');
INSERT INTO f_default_ttl VALUES('外部数据',30,'查证日期起 30 天');
INSERT INTO f_default_ttl VALUES('用户情况',180,'查证日期起 180 天');
INSERT INTO f_default_ttl VALUES('常识定律',NULL,'长期有效');
INSERT INTO f_default_ttl VALUES('其他',30,'查证日期起 30 天');

-- ========== 台账表 ==========
CREATE TABLE F(
  seq INTEGER PRIMARY KEY CHECK(seq>0),
  code TEXT NOT NULL UNIQUE GENERATED ALWAYS AS ('F-'||seq) VIRTUAL,
  内容 TEXT NOT NULL CHECK(length(trim(内容))>0),
  类别 TEXT NOT NULL,
  状态 TEXT NOT NULL,
  来源 TEXT,
  查证日期 TEXT,
  有效期 TEXT,
  有效期依据 TEXT,
  说明 TEXT,
  放行确认日期 TEXT,
  最晚解决步骤 TEXT,
  登记方式 TEXT NOT NULL DEFAULT '新增',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL
) STRICT;
CREATE TABLE D(
  seq INTEGER PRIMARY KEY CHECK(seq>0),
  code TEXT NOT NULL UNIQUE GENERATED ALWAYS AS ('D-'||seq) VIRTUAL,
  日期 TEXT NOT NULL,
  决定 TEXT NOT NULL CHECK(length(trim(决定))>0),
  理由 TEXT NOT NULL CHECK(length(trim(理由))>0),
  来源 TEXT,
  谁拍板 TEXT NOT NULL,
  状态 TEXT NOT NULL,
  作废理由 TEXT,
  类型 TEXT NOT NULL DEFAULT '决定',
  放行确认日期 TEXT,
  最晚解决步骤 TEXT,
  登记方式 TEXT NOT NULL DEFAULT '新增',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL
) STRICT;
CREATE TABLE R(
  seq INTEGER PRIMARY KEY CHECK(seq>0),
  code TEXT NOT NULL UNIQUE GENERATED ALWAYS AS ('R-'||seq) VIRTUAL,
  风险 TEXT NOT NULL CHECK(length(trim(风险))>0),
  可能性 TEXT NOT NULL,
  影响 TEXT NOT NULL,
  对策 TEXT,
  负责人 TEXT,
  状态 TEXT NOT NULL,
  说明 TEXT,
  登记方式 TEXT NOT NULL DEFAULT '新增',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL
) STRICT;
CREATE TABLE S(
  seq INTEGER PRIMARY KEY CHECK(seq>0),
  code TEXT NOT NULL UNIQUE GENERATED ALWAYS AS ('S-'||seq) VIRTUAL,
  节 INTEGER NOT NULL CHECK(节 BETWEEN 1 AND 4),
  结论 TEXT NOT NULL CHECK(length(trim(结论))>0),
  状态 TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL
) STRICT;
CREATE TABLE P(
  seq INTEGER PRIMARY KEY CHECK(seq>0),
  code TEXT NOT NULL UNIQUE GENERATED ALWAYS AS ('P-'||seq) VIRTUAL,
  步骤 TEXT NOT NULL,
  前置 TEXT,
  执行人 TEXT NOT NULL,
  完成标准 TEXT NOT NULL CHECK(完成标准 GLOB 'A-[1-9]*'),
  自验证方式 TEXT NOT NULL,
  可逆性 TEXT NOT NULL,
  派出时间 TEXT,
  回执时间 TEXT,
  截止 TEXT,
  状态 TEXT NOT NULL,
  说明 TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL
) STRICT;
CREATE TABLE A(
  rid INTEGER PRIMARY KEY,
  code TEXT NOT NULL GENERATED ALWAYS AS ('A-'||编号) VIRTUAL,
  版本代号 TEXT NOT NULL GENERATED ALWAYS AS ('A-'||编号||'v'||版本号) VIRTUAL,
  编号 INTEGER NOT NULL CHECK(编号>0),
  版本号 INTEGER NOT NULL CHECK(版本号>0),
  标准 TEXT NOT NULL,
  依据 TEXT NOT NULL,
  级别 TEXT NOT NULL,
  检查方法 TEXT NOT NULL,
  检查人 TEXT NOT NULL,
  状态 TEXT NOT NULL,
  确认日期 TEXT,
  证据 TEXT,
  说明 TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL,
  UNIQUE(编号,版本号)
) STRICT;
CREATE TABLE B(
  seq INTEGER PRIMARY KEY CHECK(seq>0),
  code TEXT NOT NULL UNIQUE GENERATED ALWAYS AS ('B-'||seq) VIRTUAL,
  bot_id TEXT NOT NULL CHECK(length(bot_id)>=8),
  名称 TEXT NOT NULL,
  类型 TEXT NOT NULL,
  所属项目 TEXT NOT NULL,
  所用模板 TEXT NOT NULL CHECK(所用模板 GLOB '*.md@v[0-9]*' OR 所用模板 GLOB '*.md@draft-[0-9a-f]*' OR 所用模板 GLOB 'http*'),
  库路径 TEXT CHECK(库路径 IS NULL OR 库路径 GLOB '/*/ledger.db'),
  状态 TEXT NOT NULL,
  创建日期 TEXT NOT NULL,
  备注 TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL
) STRICT;
CREATE TABLE dep(
  id INTEGER PRIMARY KEY,
  依赖方 TEXT NOT NULL,
  被依赖 TEXT NOT NULL,
  状态 TEXT NOT NULL DEFAULT '有效',
  说明 TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  created_by TEXT NOT NULL,
  UNIQUE(依赖方,被依赖)
) STRICT;
CREATE UNIQUE INDEX a_one_confirmed ON A(编号) WHERE 状态='用户已确认';          -- 同一 A 编号只能一行「用户已确认」（在用版本）
CREATE UNIQUE INDEX b_one_live ON B(bot_id) WHERE 状态<>'已废弃';               -- 同一 bot ID 只能一行不是「已废弃」
CREATE UNIQUE INDEX b_one_cos ON B(类型) WHERE 类型='参谋长' AND 状态='在用';   -- 在用参谋长只能一个
CREATE UNIQUE INDEX s_one_live ON S(节) WHERE 状态<>'作废';                     -- 每节只有一条在用结论

CREATE VIEW all_codes AS
  SELECT code FROM F UNION ALL SELECT code FROM D UNION ALL SELECT code FROM R UNION ALL SELECT code FROM S
  UNION ALL SELECT code FROM P UNION ALL SELECT DISTINCT code FROM A UNION ALL SELECT code FROM B;

-- ========== 日志表（只增不改不删）==========
CREATE TABLE change_log(
  id INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')),
  actor TEXT NOT NULL, reason TEXT, tbl TEXT NOT NULL, code TEXT NOT NULL, op TEXT NOT NULL CHECK(op IN ('insert','update')), old TEXT, new TEXT
) STRICT;
CREATE TABLE check_log(
  id INTEGER PRIMARY KEY, code TEXT NOT NULL GENERATED ALWAYS AS ('C-'||id) VIRTUAL,
  run_at TEXT NOT NULL, actor TEXT NOT NULL, 触发 TEXT NOT NULL, repo_tag TEXT, repo_commit TEXT, repo_clean INTEGER,
  exit_code INTEGER NOT NULL CHECK(exit_code IN (0,1,2)), 状态 TEXT NOT NULL CHECK(状态 IN ('正常','有发现','降级')),
  change_log_upto INTEGER NOT NULL, stdout TEXT NOT NULL, result_json TEXT NOT NULL CHECK(json_valid(result_json))
) STRICT;
CREATE TABLE backup_log(
  id INTEGER PRIMARY KEY, at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now','localtime')), actor TEXT NOT NULL,
  结果 TEXT NOT NULL CHECK(结果 IN ('成功','失败')), change_log_upto INTEGER NOT NULL, remote TEXT, commit_id TEXT, error TEXT
) STRICT;

-- ========== 通用护栏 ==========
CREATE TRIGGER meta_bi BEFORE INSERT ON meta BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL;
  SELECT RAISE(ABORT,'meta：schema_version、schema_tag 只能在建库或迁移时写') WHERE NEW.key IN ('schema_version','schema_tag') AND (SELECT mode FROM _ctx) NOT IN ('init','migrate');
END;
CREATE TRIGGER meta_bu BEFORE UPDATE ON meta BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL;
  SELECT RAISE(ABORT,'meta：库ID、库类型、项目名、created_at 写入后不能改') WHERE OLD.key IN ('库ID','库类型','项目名','created_at') OR NEW.key<>OLD.key;
  SELECT RAISE(ABORT,'meta：schema_version、schema_tag 只能在迁移时改') WHERE OLD.key IN ('schema_version','schema_tag') AND (SELECT mode FROM _ctx)<>'migrate';
END;
CREATE TRIGGER meta_bd BEFORE DELETE ON meta BEGIN SELECT RAISE(ABORT,'meta 不能删'); END;
CREATE TRIGGER meta_ai AFTER INSERT ON meta BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'meta',NEW.key,'insert',json_object('value',NEW.value) FROM _ctx; END;
CREATE TRIGGER meta_au AFTER UPDATE ON meta BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'meta',NEW.key,'update',json_object('value',OLD.value),json_object('value',NEW.value) FROM _ctx; END;

CREATE TRIGGER enum_bi BEFORE INSERT ON enum BEGIN SELECT RAISE(ABORT,'枚举只能在迁移时加') WHERE coalesce((SELECT mode FROM _ctx),'')<>'migrate'; END;
CREATE TRIGGER enum_bu BEFORE UPDATE ON enum BEGIN SELECT RAISE(ABORT,'枚举只能在迁移时改') WHERE coalesce((SELECT mode FROM _ctx),'')<>'migrate'; END;
CREATE TRIGGER enum_bd BEFORE DELETE ON enum BEGIN SELECT RAISE(ABORT,'枚举只能在迁移时删') WHERE coalesce((SELECT mode FROM _ctx),'')<>'migrate'; END;
CREATE TRIGGER ttl_bi BEFORE INSERT ON f_default_ttl BEGIN SELECT RAISE(ABORT,'默认有效期只能在迁移时改') WHERE coalesce((SELECT mode FROM _ctx),'')<>'migrate'; END;
CREATE TRIGGER ttl_bu BEFORE UPDATE ON f_default_ttl BEGIN SELECT RAISE(ABORT,'默认有效期只能在迁移时改') WHERE coalesce((SELECT mode FROM _ctx),'')<>'migrate'; END;
CREATE TRIGGER ttl_bd BEFORE DELETE ON f_default_ttl BEGIN SELECT RAISE(ABORT,'默认有效期只能在迁移时改') WHERE coalesce((SELECT mode FROM _ctx),'')<>'migrate'; END;

CREATE TRIGGER chg_bi BEFORE INSERT ON change_log BEGIN SELECT RAISE(ABORT,'修改记录只能由触发器写') WHERE (SELECT actor FROM _ctx) IS NULL; END;
CREATE TRIGGER chg_bu BEFORE UPDATE ON change_log BEGIN SELECT RAISE(ABORT,'修改记录不可改'); END;
CREATE TRIGGER chg_bd BEFORE DELETE ON change_log BEGIN SELECT RAISE(ABORT,'修改记录不可删'); END;
CREATE TRIGGER ck_bi BEFORE INSERT ON check_log BEGIN SELECT RAISE(ABORT,'检查日志只能由 check.py --log 写') WHERE coalesce((SELECT mode FROM _ctx),'')<>'check'; END;
CREATE TRIGGER ck_bu BEFORE UPDATE ON check_log BEGIN SELECT RAISE(ABORT,'检查日志不可改'); END;
CREATE TRIGGER ck_bd BEFORE DELETE ON check_log BEGIN SELECT RAISE(ABORT,'检查日志不可删'); END;
CREATE TRIGGER bk_bi BEFORE INSERT ON backup_log BEGIN SELECT RAISE(ABORT,'备份记录只能由 ledger.py 备份步骤写') WHERE coalesce((SELECT mode FROM _ctx),'')<>'backup'; END;
CREATE TRIGGER bk_bu BEFORE UPDATE ON backup_log BEGIN SELECT RAISE(ABORT,'备份记录不可改'); END;
CREATE TRIGGER bk_bd BEFORE DELETE ON backup_log BEGIN SELECT RAISE(ABORT,'备份记录不可删'); END;

-- ========== 各台账表的规则 ==========
CREATE TRIGGER F_bi BEFORE INSERT ON F BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'F：created_by 必须等于本次写入者') WHERE NEW.created_by IS NOT (SELECT actor FROM _ctx);
  SELECT RAISE(ABORT,'F 编号必须连续（新行 = 当前最大编号 + 1）') WHERE NEW.seq IS NOT (SELECT coalesce(max(seq),0)+1 FROM F);
  SELECT RAISE(ABORT,'F.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='F' AND col='状态');
  SELECT RAISE(ABORT,'F.类别 不是规定值') WHERE NEW.类别 NOT IN (SELECT val FROM enum WHERE tbl='F' AND col='类别');
  SELECT RAISE(ABORT,'F.登记方式 不是规定值') WHERE NEW.登记方式 NOT IN (SELECT val FROM enum WHERE tbl='F' AND col='登记方式');
  SELECT RAISE(ABORT,'F：已查证的条目必须写来源和查证日期') WHERE NEW.状态 IN ('已查证','已查证（二手）') AND (coalesce(trim(NEW.来源),'')='' OR coalesce(trim(NEW.查证日期),'')='');
  SELECT RAISE(ABORT,'F：已查证（二手）必须在说明里写试过哪些一手渠道') WHERE NEW.状态='已查证（二手）' AND coalesce(trim(NEW.说明),'')='';
  SELECT RAISE(ABORT,'F：最晚解决步骤要写成 P 编号') WHERE NEW.最晚解决步骤 IS NOT NULL AND NEW.最晚解决步骤 NOT GLOB 'P-[1-9]*';
END;
CREATE TRIGGER F_bu BEFORE UPDATE ON F BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'F.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='F' AND col='状态');
  SELECT RAISE(ABORT,'F.类别 不是规定值') WHERE NEW.类别 NOT IN (SELECT val FROM enum WHERE tbl='F' AND col='类别');
  SELECT RAISE(ABORT,'F.登记方式 不是规定值') WHERE NEW.登记方式 NOT IN (SELECT val FROM enum WHERE tbl='F' AND col='登记方式');
  SELECT RAISE(ABORT,'F：已查证的条目必须写来源和查证日期') WHERE NEW.状态 IN ('已查证','已查证（二手）') AND (coalesce(trim(NEW.来源),'')='' OR coalesce(trim(NEW.查证日期),'')='');
  SELECT RAISE(ABORT,'F：已查证（二手）必须在说明里写试过哪些一手渠道') WHERE NEW.状态='已查证（二手）' AND coalesce(trim(NEW.说明),'')='';
  SELECT RAISE(ABORT,'F：最晚解决步骤要写成 P 编号') WHERE NEW.最晚解决步骤 IS NOT NULL AND NEW.最晚解决步骤 NOT GLOB 'P-[1-9]*';
  SELECT RAISE(ABORT,'F：核心列（内容、类别、登记方式）写入后不能改，要改就新建一条并标记旧条目') WHERE NEW.seq IS NOT OLD.seq OR NEW.类别 IS NOT OLD.类别 OR NEW.登记方式 IS NOT OLD.登记方式 OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by OR ((SELECT mode FROM _ctx) IS NOT 'typo' AND (NEW.内容 IS NOT OLD.内容));
END;
CREATE TRIGGER F_bd BEFORE DELETE ON F BEGIN SELECT RAISE(ABORT,'F 只增不删：要作废就改状态'); END;
CREATE TRIGGER F_ai AFTER INSERT ON F BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'F',NEW.code,'insert',json_object('seq',NEW.seq,'内容',NEW.内容,'类别',NEW.类别,'状态',NEW.状态,'来源',NEW.来源,'查证日期',NEW.查证日期,'有效期',NEW.有效期,'有效期依据',NEW.有效期依据,'说明',NEW.说明,'放行确认日期',NEW.放行确认日期,'最晚解决步骤',NEW.最晚解决步骤,'登记方式',NEW.登记方式,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER F_au AFTER UPDATE ON F BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'F',NEW.code,'update',json_object('seq',OLD.seq,'内容',OLD.内容,'类别',OLD.类别,'状态',OLD.状态,'来源',OLD.来源,'查证日期',OLD.查证日期,'有效期',OLD.有效期,'有效期依据',OLD.有效期依据,'说明',OLD.说明,'放行确认日期',OLD.放行确认日期,'最晚解决步骤',OLD.最晚解决步骤,'登记方式',OLD.登记方式,'created_at',OLD.created_at,'created_by',OLD.created_by),json_object('seq',NEW.seq,'内容',NEW.内容,'类别',NEW.类别,'状态',NEW.状态,'来源',NEW.来源,'查证日期',NEW.查证日期,'有效期',NEW.有效期,'有效期依据',NEW.有效期依据,'说明',NEW.说明,'放行确认日期',NEW.放行确认日期,'最晚解决步骤',NEW.最晚解决步骤,'登记方式',NEW.登记方式,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER D_bi BEFORE INSERT ON D BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'D：created_by 必须等于本次写入者') WHERE NEW.created_by IS NOT (SELECT actor FROM _ctx);
  SELECT RAISE(ABORT,'D 编号必须连续（新行 = 当前最大编号 + 1）') WHERE NEW.seq IS NOT (SELECT coalesce(max(seq),0)+1 FROM D);
  SELECT RAISE(ABORT,'D.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='D' AND col='状态');
  SELECT RAISE(ABORT,'D.谁拍板 不是规定值') WHERE NEW.谁拍板 NOT IN (SELECT val FROM enum WHERE tbl='D' AND col='谁拍板');
  SELECT RAISE(ABORT,'D.类型 不是规定值') WHERE NEW.类型 NOT IN (SELECT val FROM enum WHERE tbl='D' AND col='类型');
  SELECT RAISE(ABORT,'D.登记方式 不是规定值') WHERE NEW.登记方式 NOT IN (SELECT val FROM enum WHERE tbl='D' AND col='登记方式');
  SELECT RAISE(ABORT,'D：bot 自定的决定只能是「生效（待用户确认）」等，用户确认后把谁拍板改成用户') WHERE NEW.谁拍板='bot' AND NEW.状态 IN ('生效','历史决策');
  SELECT RAISE(ABORT,'D：作废或已否决必须写作废理由') WHERE NEW.状态 IN ('作废','已否决') AND coalesce(trim(NEW.作废理由),'')='';
  SELECT RAISE(ABORT,'D：类型「候选」只在流程治理库里用') WHERE NEW.类型='候选' AND (SELECT value FROM meta WHERE key='库类型')<>'治理';
  SELECT RAISE(ABORT,'D：最晚解决步骤要写成 P 编号') WHERE NEW.最晚解决步骤 IS NOT NULL AND NEW.最晚解决步骤 NOT GLOB 'P-[1-9]*';
END;
CREATE TRIGGER D_bu BEFORE UPDATE ON D BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'D.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='D' AND col='状态');
  SELECT RAISE(ABORT,'D.谁拍板 不是规定值') WHERE NEW.谁拍板 NOT IN (SELECT val FROM enum WHERE tbl='D' AND col='谁拍板');
  SELECT RAISE(ABORT,'D.类型 不是规定值') WHERE NEW.类型 NOT IN (SELECT val FROM enum WHERE tbl='D' AND col='类型');
  SELECT RAISE(ABORT,'D.登记方式 不是规定值') WHERE NEW.登记方式 NOT IN (SELECT val FROM enum WHERE tbl='D' AND col='登记方式');
  SELECT RAISE(ABORT,'D：bot 自定的决定只能是「生效（待用户确认）」等，用户确认后把谁拍板改成用户') WHERE NEW.谁拍板='bot' AND NEW.状态 IN ('生效','历史决策');
  SELECT RAISE(ABORT,'D：作废或已否决必须写作废理由') WHERE NEW.状态 IN ('作废','已否决') AND coalesce(trim(NEW.作废理由),'')='';
  SELECT RAISE(ABORT,'D：最晚解决步骤要写成 P 编号') WHERE NEW.最晚解决步骤 IS NOT NULL AND NEW.最晚解决步骤 NOT GLOB 'P-[1-9]*';
  SELECT RAISE(ABORT,'D：核心列（日期、决定、理由、类型、登记方式）写入后不能改，要改就新建一条并标记旧条目') WHERE NEW.seq IS NOT OLD.seq OR NEW.日期 IS NOT OLD.日期 OR NEW.类型 IS NOT OLD.类型 OR NEW.登记方式 IS NOT OLD.登记方式 OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by OR ((SELECT mode FROM _ctx) IS NOT 'typo' AND (NEW.决定 IS NOT OLD.决定 OR NEW.理由 IS NOT OLD.理由));
  SELECT RAISE(ABORT,'D：谁拍板只能从 bot 改成用户') WHERE NEW.谁拍板 IS NOT OLD.谁拍板 AND NOT (OLD.谁拍板='bot' AND NEW.谁拍板='用户');
END;
CREATE TRIGGER D_bd BEFORE DELETE ON D BEGIN SELECT RAISE(ABORT,'D 只增不删：要作废就改状态'); END;
CREATE TRIGGER D_ai AFTER INSERT ON D BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'D',NEW.code,'insert',json_object('seq',NEW.seq,'日期',NEW.日期,'决定',NEW.决定,'理由',NEW.理由,'来源',NEW.来源,'谁拍板',NEW.谁拍板,'状态',NEW.状态,'作废理由',NEW.作废理由,'类型',NEW.类型,'放行确认日期',NEW.放行确认日期,'最晚解决步骤',NEW.最晚解决步骤,'登记方式',NEW.登记方式,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER D_au AFTER UPDATE ON D BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'D',NEW.code,'update',json_object('seq',OLD.seq,'日期',OLD.日期,'决定',OLD.决定,'理由',OLD.理由,'来源',OLD.来源,'谁拍板',OLD.谁拍板,'状态',OLD.状态,'作废理由',OLD.作废理由,'类型',OLD.类型,'放行确认日期',OLD.放行确认日期,'最晚解决步骤',OLD.最晚解决步骤,'登记方式',OLD.登记方式,'created_at',OLD.created_at,'created_by',OLD.created_by),json_object('seq',NEW.seq,'日期',NEW.日期,'决定',NEW.决定,'理由',NEW.理由,'来源',NEW.来源,'谁拍板',NEW.谁拍板,'状态',NEW.状态,'作废理由',NEW.作废理由,'类型',NEW.类型,'放行确认日期',NEW.放行确认日期,'最晚解决步骤',NEW.最晚解决步骤,'登记方式',NEW.登记方式,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER R_bi BEFORE INSERT ON R BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'R：created_by 必须等于本次写入者') WHERE NEW.created_by IS NOT (SELECT actor FROM _ctx);
  SELECT RAISE(ABORT,'R 编号必须连续（新行 = 当前最大编号 + 1）') WHERE NEW.seq IS NOT (SELECT coalesce(max(seq),0)+1 FROM R);
  SELECT RAISE(ABORT,'R.可能性 不是规定值') WHERE NEW.可能性 NOT IN (SELECT val FROM enum WHERE tbl='R' AND col='可能性');
  SELECT RAISE(ABORT,'R.影响 不是规定值') WHERE NEW.影响 NOT IN (SELECT val FROM enum WHERE tbl='R' AND col='影响');
  SELECT RAISE(ABORT,'R.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='R' AND col='状态');
  SELECT RAISE(ABORT,'R.登记方式 不是规定值') WHERE NEW.登记方式 NOT IN (SELECT val FROM enum WHERE tbl='R' AND col='登记方式');
  SELECT RAISE(ABORT,'R：影响为高的风险必须有对策') WHERE NEW.影响='高' AND coalesce(trim(NEW.对策),'')='';
END;
CREATE TRIGGER R_bu BEFORE UPDATE ON R BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'R.可能性 不是规定值') WHERE NEW.可能性 NOT IN (SELECT val FROM enum WHERE tbl='R' AND col='可能性');
  SELECT RAISE(ABORT,'R.影响 不是规定值') WHERE NEW.影响 NOT IN (SELECT val FROM enum WHERE tbl='R' AND col='影响');
  SELECT RAISE(ABORT,'R.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='R' AND col='状态');
  SELECT RAISE(ABORT,'R.登记方式 不是规定值') WHERE NEW.登记方式 NOT IN (SELECT val FROM enum WHERE tbl='R' AND col='登记方式');
  SELECT RAISE(ABORT,'R：影响为高的风险必须有对策') WHERE NEW.影响='高' AND coalesce(trim(NEW.对策),'')='';
  SELECT RAISE(ABORT,'R：核心列（风险、对策、登记方式）写入后不能改，要改就新建一条并标记旧条目') WHERE NEW.seq IS NOT OLD.seq OR NEW.登记方式 IS NOT OLD.登记方式 OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by OR ((SELECT mode FROM _ctx) IS NOT 'typo' AND (NEW.风险 IS NOT OLD.风险 OR NEW.对策 IS NOT OLD.对策));
END;
CREATE TRIGGER R_bd BEFORE DELETE ON R BEGIN SELECT RAISE(ABORT,'R 只增不删：要作废就改状态'); END;
CREATE TRIGGER R_ai AFTER INSERT ON R BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'R',NEW.code,'insert',json_object('seq',NEW.seq,'风险',NEW.风险,'可能性',NEW.可能性,'影响',NEW.影响,'对策',NEW.对策,'负责人',NEW.负责人,'状态',NEW.状态,'说明',NEW.说明,'登记方式',NEW.登记方式,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER R_au AFTER UPDATE ON R BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'R',NEW.code,'update',json_object('seq',OLD.seq,'风险',OLD.风险,'可能性',OLD.可能性,'影响',OLD.影响,'对策',OLD.对策,'负责人',OLD.负责人,'状态',OLD.状态,'说明',OLD.说明,'登记方式',OLD.登记方式,'created_at',OLD.created_at,'created_by',OLD.created_by),json_object('seq',NEW.seq,'风险',NEW.风险,'可能性',NEW.可能性,'影响',NEW.影响,'对策',NEW.对策,'负责人',NEW.负责人,'状态',NEW.状态,'说明',NEW.说明,'登记方式',NEW.登记方式,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER S_bi BEFORE INSERT ON S BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'S：created_by 必须等于本次写入者') WHERE NEW.created_by IS NOT (SELECT actor FROM _ctx);
  SELECT RAISE(ABORT,'S 编号必须连续（新行 = 当前最大编号 + 1）') WHERE NEW.seq IS NOT (SELECT coalesce(max(seq),0)+1 FROM S);
  SELECT RAISE(ABORT,'S.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='S' AND col='状态');
END;
CREATE TRIGGER S_bu BEFORE UPDATE ON S BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'S.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='S' AND col='状态');
  SELECT RAISE(ABORT,'S：核心列（节、结论）写入后不能改，要改就新建一条并标记旧条目') WHERE NEW.seq IS NOT OLD.seq OR NEW.节 IS NOT OLD.节 OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by OR ((SELECT mode FROM _ctx) IS NOT 'typo' AND (NEW.结论 IS NOT OLD.结论));
END;
CREATE TRIGGER S_bd BEFORE DELETE ON S BEGIN SELECT RAISE(ABORT,'S 只增不删：要作废就改状态'); END;
CREATE TRIGGER S_ai AFTER INSERT ON S BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'S',NEW.code,'insert',json_object('seq',NEW.seq,'节',NEW.节,'结论',NEW.结论,'状态',NEW.状态,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER S_au AFTER UPDATE ON S BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'S',NEW.code,'update',json_object('seq',OLD.seq,'节',OLD.节,'结论',OLD.结论,'状态',OLD.状态,'created_at',OLD.created_at,'created_by',OLD.created_by),json_object('seq',NEW.seq,'节',NEW.节,'结论',NEW.结论,'状态',NEW.状态,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER P_bi BEFORE INSERT ON P BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'P：created_by 必须等于本次写入者') WHERE NEW.created_by IS NOT (SELECT actor FROM _ctx);
  SELECT RAISE(ABORT,'P 编号必须连续（新行 = 当前最大编号 + 1）') WHERE NEW.seq IS NOT (SELECT coalesce(max(seq),0)+1 FROM P);
  SELECT RAISE(ABORT,'P.可逆性 不是规定值') WHERE NEW.可逆性 NOT IN (SELECT val FROM enum WHERE tbl='P' AND col='可逆性');
  SELECT RAISE(ABORT,'P.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='P' AND col='状态');
  SELECT RAISE(ABORT,'P：有回执时间就必须有派出时间') WHERE NEW.回执时间 IS NOT NULL AND NEW.派出时间 IS NULL;
END;
CREATE TRIGGER P_bu BEFORE UPDATE ON P BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'P.可逆性 不是规定值') WHERE NEW.可逆性 NOT IN (SELECT val FROM enum WHERE tbl='P' AND col='可逆性');
  SELECT RAISE(ABORT,'P.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='P' AND col='状态');
  SELECT RAISE(ABORT,'P：有回执时间就必须有派出时间') WHERE NEW.回执时间 IS NOT NULL AND NEW.派出时间 IS NULL;
  SELECT RAISE(ABORT,'P：核心列（完成标准、自验证方式、可逆性）写入后不能改，要改就新建一条并标记旧条目') WHERE NEW.seq IS NOT OLD.seq OR NEW.完成标准 IS NOT OLD.完成标准 OR NEW.可逆性 IS NOT OLD.可逆性 OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by OR ((SELECT mode FROM _ctx) IS NOT 'typo' AND (NEW.自验证方式 IS NOT OLD.自验证方式));
END;
CREATE TRIGGER P_bd BEFORE DELETE ON P BEGIN SELECT RAISE(ABORT,'P 只增不删：要作废就改状态'); END;
CREATE TRIGGER P_ai AFTER INSERT ON P BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'P',NEW.code,'insert',json_object('seq',NEW.seq,'步骤',NEW.步骤,'前置',NEW.前置,'执行人',NEW.执行人,'完成标准',NEW.完成标准,'自验证方式',NEW.自验证方式,'可逆性',NEW.可逆性,'派出时间',NEW.派出时间,'回执时间',NEW.回执时间,'截止',NEW.截止,'状态',NEW.状态,'说明',NEW.说明,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER P_au AFTER UPDATE ON P BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'P',NEW.code,'update',json_object('seq',OLD.seq,'步骤',OLD.步骤,'前置',OLD.前置,'执行人',OLD.执行人,'完成标准',OLD.完成标准,'自验证方式',OLD.自验证方式,'可逆性',OLD.可逆性,'派出时间',OLD.派出时间,'回执时间',OLD.回执时间,'截止',OLD.截止,'状态',OLD.状态,'说明',OLD.说明,'created_at',OLD.created_at,'created_by',OLD.created_by),json_object('seq',NEW.seq,'步骤',NEW.步骤,'前置',NEW.前置,'执行人',NEW.执行人,'完成标准',NEW.完成标准,'自验证方式',NEW.自验证方式,'可逆性',NEW.可逆性,'派出时间',NEW.派出时间,'回执时间',NEW.回执时间,'截止',NEW.截止,'状态',NEW.状态,'说明',NEW.说明,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER A_bi BEFORE INSERT ON A BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'A：created_by 必须等于本次写入者') WHERE NEW.created_by IS NOT (SELECT actor FROM _ctx);
  SELECT RAISE(ABORT,'A：新编号必须等于当前最大编号 + 1') WHERE NOT EXISTS(SELECT 1 FROM A WHERE 编号=NEW.编号) AND NEW.编号 <> (SELECT coalesce(max(编号),0)+1 FROM A);
  SELECT RAISE(ABORT,'A：同一编号的新版本号必须等于当前最大版本号 + 1（新编号从 1 开始）') WHERE NEW.版本号 <> (SELECT coalesce(max(版本号),0)+1 FROM A WHERE 编号=NEW.编号);
  SELECT RAISE(ABORT,'A.级别 不是规定值') WHERE NEW.级别 NOT IN (SELECT val FROM enum WHERE tbl='A' AND col='级别');
  SELECT RAISE(ABORT,'A.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='A' AND col='状态');
  SELECT RAISE(ABORT,'A：用户已确认必须写确认日期') WHERE NEW.状态='用户已确认' AND coalesce(trim(NEW.确认日期),'')='';
END;
CREATE TRIGGER A_bu BEFORE UPDATE ON A BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'A.级别 不是规定值') WHERE NEW.级别 NOT IN (SELECT val FROM enum WHERE tbl='A' AND col='级别');
  SELECT RAISE(ABORT,'A.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='A' AND col='状态');
  SELECT RAISE(ABORT,'A：用户已确认必须写确认日期') WHERE NEW.状态='用户已确认' AND coalesce(trim(NEW.确认日期),'')='';
  SELECT RAISE(ABORT,'A：核心列（编号、版本号、标准、依据、级别、检查方法）写入后不能改，要改就新建一条并标记旧条目') WHERE NEW.rid IS NOT OLD.rid OR NEW.编号 IS NOT OLD.编号 OR NEW.版本号 IS NOT OLD.版本号 OR NEW.级别 IS NOT OLD.级别 OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by OR ((SELECT mode FROM _ctx) IS NOT 'typo' AND (NEW.标准 IS NOT OLD.标准 OR NEW.依据 IS NOT OLD.依据 OR NEW.检查方法 IS NOT OLD.检查方法));
END;
CREATE TRIGGER A_bd BEFORE DELETE ON A BEGIN SELECT RAISE(ABORT,'A 只增不删：要作废就改状态'); END;
CREATE TRIGGER A_ai AFTER INSERT ON A BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'A',NEW.版本代号,'insert',json_object('rid',NEW.rid,'编号',NEW.编号,'版本号',NEW.版本号,'标准',NEW.标准,'依据',NEW.依据,'级别',NEW.级别,'检查方法',NEW.检查方法,'检查人',NEW.检查人,'状态',NEW.状态,'确认日期',NEW.确认日期,'证据',NEW.证据,'说明',NEW.说明,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER A_au AFTER UPDATE ON A BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'A',NEW.版本代号,'update',json_object('rid',OLD.rid,'编号',OLD.编号,'版本号',OLD.版本号,'标准',OLD.标准,'依据',OLD.依据,'级别',OLD.级别,'检查方法',OLD.检查方法,'检查人',OLD.检查人,'状态',OLD.状态,'确认日期',OLD.确认日期,'证据',OLD.证据,'说明',OLD.说明,'created_at',OLD.created_at,'created_by',OLD.created_by),json_object('rid',NEW.rid,'编号',NEW.编号,'版本号',NEW.版本号,'标准',NEW.标准,'依据',NEW.依据,'级别',NEW.级别,'检查方法',NEW.检查方法,'检查人',NEW.检查人,'状态',NEW.状态,'确认日期',NEW.确认日期,'证据',NEW.证据,'说明',NEW.说明,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER B_bi BEFORE INSERT ON B BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'B：created_by 必须等于本次写入者') WHERE NEW.created_by IS NOT (SELECT actor FROM _ctx);
  SELECT RAISE(ABORT,'B 编号必须连续（新行 = 当前最大编号 + 1）') WHERE NEW.seq IS NOT (SELECT coalesce(max(seq),0)+1 FROM B);
  SELECT RAISE(ABORT,'B.类型 不是规定值') WHERE NEW.类型 NOT IN (SELECT val FROM enum WHERE tbl='B' AND col='类型');
  SELECT RAISE(ABORT,'B.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='B' AND col='状态');
  SELECT RAISE(ABORT,'B：bot 名册只在流程治理库里') WHERE (SELECT value FROM meta WHERE key='库类型')<>'治理';
  SELECT RAISE(ABORT,'B：副官必须写所属项目，不能是共用') WHERE NEW.类型='副官' AND NEW.所属项目='共用';
  SELECT RAISE(ABORT,'B：参谋长的所属项目必须是流程治理') WHERE NEW.类型='参谋长' AND NEW.所属项目<>'流程治理';
  SELECT RAISE(ABORT,'B：在用的参谋长、副官必须登记库路径') WHERE NEW.类型 IN ('参谋长','副官') AND NEW.状态='在用' AND coalesce(NEW.库路径,'')='';
  SELECT RAISE(ABORT,'B：库路径必须是 <数据根目录>/<所属项目>/ledger.db') WHERE NEW.库路径 IS NOT NULL AND substr(NEW.库路径,-length('/'||NEW.所属项目||'/ledger.db')) IS NOT '/'||NEW.所属项目||'/ledger.db';
END;
CREATE TRIGGER B_bu BEFORE UPDATE ON B BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'B.类型 不是规定值') WHERE NEW.类型 NOT IN (SELECT val FROM enum WHERE tbl='B' AND col='类型');
  SELECT RAISE(ABORT,'B.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='B' AND col='状态');
  SELECT RAISE(ABORT,'B：副官必须写所属项目，不能是共用') WHERE NEW.类型='副官' AND NEW.所属项目='共用';
  SELECT RAISE(ABORT,'B：参谋长的所属项目必须是流程治理') WHERE NEW.类型='参谋长' AND NEW.所属项目<>'流程治理';
  SELECT RAISE(ABORT,'B：在用的参谋长、副官必须登记库路径') WHERE NEW.类型 IN ('参谋长','副官') AND NEW.状态='在用' AND coalesce(NEW.库路径,'')='';
  SELECT RAISE(ABORT,'B：库路径必须是 <数据根目录>/<所属项目>/ledger.db') WHERE NEW.库路径 IS NOT NULL AND substr(NEW.库路径,-length('/'||NEW.所属项目||'/ledger.db')) IS NOT '/'||NEW.所属项目||'/ledger.db';
  SELECT RAISE(ABORT,'B：核心列（bot_id、类型）写入后不能改，要改就新建一条并标记旧条目') WHERE NEW.seq IS NOT OLD.seq OR NEW.bot_id IS NOT OLD.bot_id OR NEW.类型 IS NOT OLD.类型 OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by;
END;
CREATE TRIGGER B_bd BEFORE DELETE ON B BEGIN SELECT RAISE(ABORT,'B 只增不删：要作废就改状态'); END;
CREATE TRIGGER B_ai AFTER INSERT ON B BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'B',NEW.code,'insert',json_object('seq',NEW.seq,'bot_id',NEW.bot_id,'名称',NEW.名称,'类型',NEW.类型,'所属项目',NEW.所属项目,'所用模板',NEW.所用模板,'库路径',NEW.库路径,'状态',NEW.状态,'创建日期',NEW.创建日期,'备注',NEW.备注,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER B_au AFTER UPDATE ON B BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'B',NEW.code,'update',json_object('seq',OLD.seq,'bot_id',OLD.bot_id,'名称',OLD.名称,'类型',OLD.类型,'所属项目',OLD.所属项目,'所用模板',OLD.所用模板,'库路径',OLD.库路径,'状态',OLD.状态,'创建日期',OLD.创建日期,'备注',OLD.备注,'created_at',OLD.created_at,'created_by',OLD.created_by),json_object('seq',NEW.seq,'bot_id',NEW.bot_id,'名称',NEW.名称,'类型',NEW.类型,'所属项目',NEW.所属项目,'所用模板',NEW.所用模板,'库路径',NEW.库路径,'状态',NEW.状态,'创建日期',NEW.创建日期,'备注',NEW.备注,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER dep_bi BEFORE INSERT ON dep BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'dep：created_by 必须等于本次写入者') WHERE NEW.created_by IS NOT (SELECT actor FROM _ctx);
  SELECT RAISE(ABORT,'dep.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='dep' AND col='状态');
  SELECT RAISE(ABORT,'依赖：不能依赖自己') WHERE NEW.依赖方 = NEW.被依赖;
  SELECT RAISE(ABORT,'依赖：依赖方编号不存在') WHERE NOT EXISTS(SELECT 1 FROM all_codes WHERE code=NEW.依赖方);
  SELECT RAISE(ABORT,'依赖：被依赖编号不存在') WHERE NOT EXISTS(SELECT 1 FROM all_codes WHERE code=NEW.被依赖);
END;
CREATE TRIGGER dep_bu BEFORE UPDATE ON dep BEGIN
  SELECT RAISE(ABORT,'只能经 ledger.py 写入（写入者未设置）') WHERE (SELECT actor FROM _ctx) IS NULL OR (SELECT mode FROM _ctx) NOT IN ('write','init','migrate','typo');
  SELECT RAISE(ABORT,'dep.状态 不是规定值') WHERE NEW.状态 NOT IN (SELECT val FROM enum WHERE tbl='dep' AND col='状态');
  SELECT RAISE(ABORT,'依赖：不能依赖自己') WHERE NEW.依赖方 = NEW.被依赖;
  SELECT RAISE(ABORT,'dep：核心列（依赖方、被依赖）写入后不能改，要改就新建一条并标记旧条目') WHERE NEW.id IS NOT OLD.id OR NEW.依赖方 IS NOT OLD.依赖方 OR NEW.被依赖 IS NOT OLD.被依赖 OR NEW.created_at IS NOT OLD.created_at OR NEW.created_by IS NOT OLD.created_by;
  SELECT RAISE(ABORT,'依赖：只能从有效改成作废') WHERE NEW.状态 IS NOT OLD.状态 AND NOT (OLD.状态='有效' AND NEW.状态='作废');
END;
CREATE TRIGGER dep_bd BEFORE DELETE ON dep BEGIN SELECT RAISE(ABORT,'dep 只增不删：要作废就改状态'); END;
CREATE TRIGGER dep_ai AFTER INSERT ON dep BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,new) SELECT actor,reason,'dep','dep-'||NEW.id,'insert',json_object('id',NEW.id,'依赖方',NEW.依赖方,'被依赖',NEW.被依赖,'状态',NEW.状态,'说明',NEW.说明,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
CREATE TRIGGER dep_au AFTER UPDATE ON dep BEGIN INSERT INTO change_log(actor,reason,tbl,code,op,old,new) SELECT actor,reason,'dep','dep-'||NEW.id,'update',json_object('id',OLD.id,'依赖方',OLD.依赖方,'被依赖',OLD.被依赖,'状态',OLD.状态,'说明',OLD.说明,'created_at',OLD.created_at,'created_by',OLD.created_by),json_object('id',NEW.id,'依赖方',NEW.依赖方,'被依赖',NEW.被依赖,'状态',NEW.状态,'说明',NEW.说明,'created_at',NEW.created_at,'created_by',NEW.created_by) FROM _ctx; END;
-- 表结构版本由 ledger.py 建库时写进 meta（schema_version=本文件头的版本号，schema_tag=建库时克隆所在的 tag；克隆不在 tag 上时是完整提交号）。
