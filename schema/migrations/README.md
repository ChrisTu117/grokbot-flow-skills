# 表结构迁移文件

- `schema/schema.sql` 永远是当前版本的完整建库脚本，头部 `-- schema_version: N` 是版本号。
- 版本 N-1 → N 的迁移写在 `NNN.sql`（三位数字，如 `002.sql`），第一行注释写「从 N-1 到 N」。schema 1 是 v1.0.0 草稿演练时的版本；v1.0.0 正式发布是 schema 2（`002.sql`：新增摩擦 M 表）。
- 每个发布过的旧版完整建库脚本留档在 `schema/history/v<N>.sql`（不改），自测用它建旧库、跑迁移、和新建库比对。
- 由 `ledger.py migrate --project X --to N --actor <ID> --approved "用户原话 + 日期"` 执行，流程是：
  1. 先用备份接口快照，标签 `migrate-to-N`；
  2. 一个 `BEGIN IMMEDIATE` 事务，写入模式 migrate；
  3. 删掉库里**全部**触发器、视图和显式索引（只删引用这张表的不够：`dep` 的触发器引用视图 `all_codes`）；
  4. 按顺序执行各迁移文件；
  5. 按新版 `schema.sql` 重建全部触发器、视图、索引；
  6. 改 `schema_version`、`schema_tag`，记一条 D（类型「版本」）；
  7. 和用新版 `schema.sql` 新建的库逐条比（表、触发器、索引、视图、枚举、默认有效期），不一致或 `foreign_key_check` 不过就整体回滚；
  8. 提交后跑 `integrity_check`，推备份。
- 迁移文件只写数据和表本身的改动，**每条语句单独占行尾**（脚本按完整语句切分，一行里写两条会报错）：
  - 只加状态值或默认值：`INSERT INTO enum …` / `INSERT INTO f_default_ttl …`。
  - 改列或改约束（SQLite 改不了已有 CHECK）：`ALTER TABLE X RENAME TO X_old;` → 原样贴新版 `schema.sql` 里的 `CREATE TABLE X(…)` → `INSERT INTO X(列…) SELECT 列… FROM X_old;` → `DROP TABLE X_old;`。新表的建表语句必须和 `schema.sql` 逐字一致，否则第 7 步比对不过。
- X 版本（改表结构）发布前必须附迁移文件，并在 `ledger.py selftest` 里加「旧库迁移后 = 新建库」的用例。
- 发布前用 `ledger.py migrate-dryrun --project X --to N --out DIR` 在每个已登记库的拷贝上演练（真库不动），见治理 skill 第 4d 节。
