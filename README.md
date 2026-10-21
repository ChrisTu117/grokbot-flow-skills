# grokbot-flow-skills

参谋长流程的维护中心：skill、bot 模板、台账表结构、写入脚本、检查脚本都在这里。版本和修改记录全在 git：整个仓库一个版本号，用带说明的 tag `vX.Y.Z`，没打 tag 的提交不算发布。

| 目录 | 内容 |
|---|---|
| `skills/<目录>/SKILL.md` | 四个 skill（本机 skill 名用英文 name，中文名加载不到）：上手 `flow-onboarding`（`onboarding/`）、创世 `flow-genesis`（`genesis/`）、参谋长治理 `flow-chief-governance`（`chief-of-staff-governance/`）、通用流程 `flow-general`（`general-flow/`） |
| `templates/` | bot 模板，一个文件一个模板，只放设定正文；说明见 `templates/README.md`；定时任务标准指令 `templates/routines.md` |
| `schema/schema.sql`、`schema/migrations/`、`schema/history/` | 台账表结构（SQLite，一项目一个库）、各版本迁移文件、发布过的旧版建库脚本留档 |
| `scripts/ledger.py` | 台账唯一写入口：核对写入者、个人信息拦截、快照、每次写后导出 SQL 推备份；只读查表、贴 Markdown 表、跨库摩擦汇总、迁移演练 |
| `scripts/check.py` | 检查脚本（只读查库：规则齐全、编号、行数、写入者、备份；本机对仓库比对；名册对平台；创世盘点 inventory；副官检查时报「参谋长可能停了」） |
| `tests/` | 压力测试和触发测试的题目、跑法、评分和对比（`python3 tests/run.py all`，见 `tests/README.md`） |
| `build/hash.py` | 规范化哈希（`--diff` 找出两份文本第一处不同），检查脚本直接调用 |

台账放在 `/home/box/flow-data/<项目名>/ledger.db`，每次写入后由 ledger.py 导出 SQL 推到私有备份仓库 `flow-ledger-backup`（一个项目一个子目录）。

## 怎么装

参谋长把本仓库克隆到 `/home/box/flow-repo` 并切到最新 tag（克隆已存在就只 fetch 不切，停在旧 tag、不在 tag 上或有本地改动时先停下问用户，见创世第 0 节），然后直接按克隆里的 `skills/genesis/SKILL.md` 执行创世，不先手动装 skill：盘点、你确认一次之后，创世第 4 节才从克隆装 skill、建 bot、建定时任务、建台账。首次引导写在 `templates/chief-of-staff.md`。安装细则见 `skills/genesis/SKILL.md` 第 0、4 节；之后的发布和升级见 `skills/chief-of-staff-governance/SKILL.md` 第 4 节。

## 计算哈希

规范化 v2：frontmatter 只取 name、description 两个值，按固定两行重写（没有 frontmatter 的文件不加）；正文换行统一为 LF → 去掉每行行尾空白 → 去掉首尾空行 → SHA-256。哈希不登记在任何地方，要核对就现算：

```
python3 build/hash.py skills/<slug>/SKILL.md
python3 scripts/check.py run --project 流程治理 --actor <bot ID> --trigger 手动 --governance
python3 scripts/check.py selftest
python3 scripts/ledger.py selftest
```
