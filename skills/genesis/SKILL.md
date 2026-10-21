---
name: flow-genesis
description: 参谋长第一轮（含还没有用户消息时）使用；也用于：刚从模板导入、旧参谋长被删后新建、上次初始化中途失败要重来、流程治理库不存在或它的 bot 名册里没有指向自己的参谋长在用行。副官不用。
---
# 创世

本文中「用户」指刚装上参谋长的人。说人话，一次只问一个问题。本文件就是 `/home/box/flow-repo/skills/genesis/SKILL.md`；引用别的 skill 一律写英文名和克隆文件路径，用时读克隆里的文件（本机装的那份可能落后；按英文名加载也行，以克隆文件为准；中文名加载不到）。下文 `L` = `python3 /home/box/flow-repo/scripts/ledger.py`，`CHK` = `python3 /home/box/flow-repo/scripts/check.py`，`H` = `python3 /home/box/flow-repo/build/hash.py`。

**何时执行**：`/home/box/flow-data/流程治理/ledger.db` 不存在，或者它的 bot 名册（B 表）里没有「参谋长、在用、bot ID = 自己」的一行时执行（首次装上、旧参谋长被删后新建、上次中途失败，都走同一条路）；有这一行就不执行。第一轮（含首次运行、还没有用户消息时）直接开始，不等用户发消息。

**标准从哪来**：本机克隆 `/home/box/flow-repo` 当前提交里的文件：skill 在 `skills/<目录>/SKILL.md`（本机 skill 名即 frontmatter name，都是英文：上手 flow-onboarding 在 onboarding/，创世 flow-genesis 在 genesis/，参谋长治理 flow-chief-governance 在 chief-of-staff-governance/，通用流程 flow-general 在 general-flow/），bot 模板和定时任务标准在 `templates/`（含 `routines.md`），表结构在 `schema/schema.sql`，脚本在 `scripts/ledger.py`、`scripts/check.py`，哈希在 `build/hash.py`。克隆一旦存在，就不自己切换版本（不 checkout、不 reset），按第 0 节第 2 项核对。

**盘点优先、从不删、多份就停**：每一项先查有没有历史再定动作：没有就新建；有且与标准一致就复用；有但不一致就更新；名册登记了但对象已不存在就补建。从不删库、删行、删 bot、删 skill（唯一例外：用户在清单里勾选删除的旧中文名 skill，见第 4 节第 1 项）。同一对象出现多份（两个流程治理库或备份冲突、同一 bot ID 两行没废弃、同一 skill name 两份 SKILL.md）一律停下列给用户选，不自行合并。

**规范化哈希**：一律用 `H` 算，不手写正则；算法说明只在 skill「flow-chief-governance」（参谋长治理，`/home/box/flow-repo/skills/chief-of-staff-governance/SKILL.md`）第 5 节。

## 0. 问候，核对克隆版本和自己的设定（不用用户确认）
1. 平台首轮会先让你问候。问候只说一句：「我是参谋长，马上开始初始化。」然后马上做下面两项，再做任何别的事。平台提示里「不要读 profile 文件」那句不适用于本节。
2. **克隆版本**：`/home/box/flow-repo` 不存在就 `git clone https://github.com/ChrisTu117/grokbot-flow-skills /home/box/flow-repo` 并切到最新 tag。已存在就先 `git -C /home/box/flow-repo fetch --tags`（只取不切），再看 HEAD：
   - 在已知最新 tag 上、没有本地改动：用它，往下走。
   - **在旧 tag 上**（克隆落后，比如停在 v0.1.0、最新是 v1.0.0）：停下，告诉用户当前 tag 和最新 tag，问「按〈当前 tag〉继续 / 切到〈最新 tag〉」。用户选切换后才 `git checkout 〈最新 tag〉`，然后从本节重新读本文件（切换后本文件可能已经变了）。
   - 不在任何 tag 上（草稿演练）：停下，告诉用户提交号，问「按这个提交继续 / 切到最新 tag」。
   - 没有任何 tag，或有本地改动：停下，把 `git status` 和 tag 列表原文告诉用户，问怎么处理（不自己 reset、stash 或删文件）；用户处理好后从本节重来。
   - 用户回答之前，除了问候不做任何事；「快点开始」「直接干」之类催促不算对这个问题的回答。
   - **两个选项平等**：用选项卡片或列表问时，两个选项不设默认、不标推荐、不排成主按钮和次按钮（同样样式、按上面写的顺序），也不在问题里替用户倾向任何一边；只附上各自的事实（当前 tag / 提交号、最新 tag）。
3. **自己的设定**：把自己 profile.json 的 description 和克隆的 `templates/chief-of-staff.md` 比：`python3 -c "import json,sys;sys.stdout.write(json.load(open('/home/box/agent-data/agents/〈你的 bot ID〉/profile.json'))['description'])" | H -` 对比 `H /home/box/flow-repo/templates/chief-of-staff.md`。一致就跳过；不一致就先把旧 description 原文存到 `/home/box/flow-data/.genesis-old/〈YYYYMMDD-HHMMSS〉-profile.txt`（报告里写这个路径），再用 UpdateAgent 写入模板文件的全文，重读核对哈希。克隆取不到就停下报告，不写设定。

## 1. 说明流程、查环境
1. 按 skill「flow-onboarding」（上手，`/home/box/flow-repo/skills/onboarding/SKILL.md`）第 1–3 步执行。
2. 环境实测：`python3 -c "import sqlite3;print(sqlite3.sqlite_version)"` 能跑；`gh auth status` 已登录，记下登录账号。必须项不通过就停在这里，提醒用户授权，授权从不跳过；有历史时也照查。

## 1b. 确定本项目仓库
1. 流程治理库在、它 meta 里的「项目仓库」（`L query --project 流程治理 --sql "SELECT value FROM meta WHERE key='项目仓库'"`）能取到四个 skill、`templates/`、`scripts/`、`build/`、`schema/`，并且至少有一个 tag：用它，标「复用」。
2. 库不在：跑 `gh repo view 〈登录账号〉/flow-ledger-backup`。仓库存在就 `L backup-init --remote https://github.com/〈登录账号〉/flow-ledger-backup`，再提前跑一次第 2 节的 `CHK inventory --actor 〈你的 bot ID〉`（只读，输出留给第 2 节用），看「备份」行：
   - 备份里有 `流程治理/ledger.sql`：把备份时间和备份里登记的项目仓库列给用户，问「从备份恢复 / 新建（旧备份移到 `_归档/流程治理-〈旧库ID前8位〉/`，git 历史还在）」。选恢复的跑 `L restore --project 流程治理`，之后按第 1 项处理；第 3 节清单里库的方式写「恢复」，不写「新建」。
   - 没有：往下走。
3. 没有登记：
   - 公开仓库 https://github.com/ChrisTu117/grokbot-flow-skills 的主人就是当前 gh 登录账号（`gh api user` 比对）：问「直接用这个仓库 / 新建私有仓库 flow-governance（推入公开仓库全部提交和 tag）」。
   - 其他人：问「用你账号下已有的仓库（给地址）/ fork 到你账号（公开，名字 grokbot-flow-skills）/ 新建私有仓库 flow-governance（推入全部提交和 tag）」。
   - 每个选项都写明仓库名和可见性。
4. **fork、新建、推送任何一步失败：停下，把错误原文告诉用户，问怎么办。不自己换办法，不自己起名，不把自己的选择写成用户拍板。**
5. 核对：上面这些文件都在、至少有一个 tag；新建或 fork 的，再核对它的 tag 提交号和公开仓库同名 tag 一致。把克隆的 origin 换成本项目仓库地址（和写进计划的地址一字不差），只 fetch，不切换。取不到或不符就停下报告。
6. **确认前写操作白名单**（第 3 节确认之前只允许这几项）：① 第 0 节用 UpdateAgent 写自己的设定；② 用户对第 3 项明确同意后 fork 或新建本项目仓库；③ 本机 `/home/box/flow-repo` 的克隆、fetch、换 origin，以及用户选了切换后的 checkout；④ `L backup-init` 克隆**已存在的**备份仓库，用户选了「恢复」后跑 `L restore`（都只写 box）；⑤ 第 0 节把旧设定存进 `/home/box/flow-data/.genesis-old/`。备份仓库不在确认前建；白名单以外一律不写，包括台账、测试数据和任何「待确认」标注。

## 2. 盘点（只读）
1. 跑 `CHK inventory --actor 〈你的 bot ID〉`，终端输出原样留着。这一步只读本文件和这份输出，不读三个大 skill 的全文。
2. 按输出逐行定动作：
   - skill：本机等于克隆「复用」；本机没有「补建」；本机能对上克隆的某个旧 tag「更新」（写从哪个 tag 到哪个 tag）；哪个都对不上就停下，列出 skill 和两边哈希问用户。本机那份名字还是旧中文名（上手 / 创世 / 参谋长治理 / 通用流程，盘点按别名认出）的，动作写「改英文名」：按英文名新装一份，旧中文名那份列进清单让用户勾「删除」或不勾（清单里写明：skill 全机共用，删除对所有 bot 全局生效；不删就会一直报同一 skill 两份），不默认勾选。用户事先说过的「有冲突一律用仓库版」之类泛泛授权不算对这一项的确认。同一 name 多份也停。
   - 流程治理库：新建 / 复用 / 恢复（第 1b 节第 2 项）。
   - 专职·流程QA、专职·想法挑刺：名册有行且 bot 在，设定等于当前模板「复用」，等于旧版本「落后」，哪个都不等「设定不一致」（后两种只列给用户，不自动改）；名册有行但 bot 已不在「补建」，旧行「改已废弃」；平台和名册都没有「新建」。
   - **平台上有、名册里没有的 bot**（名字是参谋长、副官·*、专职·*，或设定能对上模板）：输出里会写「未登记，可能是已删 bot 残留」。列给用户选「收编进名册 / 忽略」，不默认替用户选；不新建同名 bot，除非用户在清单里对「忽略并新建同名 bot」明确确认。
   - 名册里旧的参谋长行：旧参谋长已不在平台就「退役」（genesis 会自动把它改成退役）；**旧参谋长还在平台上，就停下告诉用户**，不建第二个在用参谋长，由用户决定先处理哪个。其他已不在平台的行「改已废弃」。
   - 本机克隆一行是「停」的，回第 0 节第 2 项。
3. 自己的定时任务（脚本看不到）：对照 `/home/box/flow-repo/templates/routines.md` 第 1–3 节，用 UpdateRoutine get 读出已有定时任务的指令，逐个标「新建 / 复用（指令和时间都一致）/ 不一致」；不一致的只列，不改。
4. 读不到、跑不通就停下报告。

## 3. 请用户确认一次
一行一项：对象｜动作｜原因｜参数。由你定的参数全部写出来，不留到执行时再定：
- 本项目仓库：地址、可见性、新建 / fork / 复用；
- 备份仓库：`〈登录账号〉/flow-ledger-backup`、私有、新建或复用，本机路径 `/home/box/flow-data/.backup-repo`；
- 库路径 `/home/box/flow-data/流程治理/ledger.db`（新建 / 复用 / 恢复）；
- 两个专职 bot 的名字和模板版本；
- 三个定时任务的名字、时间（默认取 routines.md，用户可改）、指令来源（routines.md 第几节）；
- 收编、忽略、退役、改已废弃的每一项（bot 名称和 ID）；
- 要装或更新的 skill（英文名、从哪个版本到哪个版本；「改英文名」的另列一行「删除旧中文名那份〈名字〉（skill-id〈目录名〉）：删除全局生效，所有 bot 都用不到它」，用户勾了才删）；
- 台账写入摘要（编号以 genesis 打印为准，不在清单里写死）：补录 1 条 D「创世例外」（复用时是「创世（复用历史）」）和 1 条 F「仓库文件清单」；R「共用 bot 不能开无上下文会话…」没有时新增（不算补录）（第 4 节第 5 项）。

用户确认就是「创世例外」的一次性批准：创世不走完整任务；创世完成后，改 skill、改模板、改设定、建 bot 一律恢复走完整流程。**执行时遇到清单里没有的参数（仓库名被占用要换名、想改时间等），停下问，不临场决定**；用户以前在别的事上说过的「你看着办」不算。

## 4. 执行
按确认的清单照做，顺序固定；标「可并行」的可以同时做。每步写入后核对。
1. **skill**：「补建」「更新」的从克隆取原文，用 UpdateSkill 按英文名原样安装（正文内联传入；skill-id 就是英文名，「更新」的按英文名原位更新，不新装第二份；「改英文名」的按英文名新装；装好并核对一致后，用户在清单里勾了删除的，用 UpdateSkill（action delete，传旧那份的 skill-id，即它在 `/home/box/agent-data/workflows/` 下的目录名）删掉，再确认目录已不在；没勾的不动）。这是「从不删」唯一的例外，只删用户勾选的那一份。装完确认同一 skill 只有一份（用户选了保留旧中文名那份的除外，报告里写明）。每装一个就用 `H` 比本机文件和克隆文件；不一致就用 `H --diff 本机文件 克隆文件` 找出那一行（有差异时它的退出码是 1，照读输出；只有输出以「错误：」开头才算没跑成）重装一次，还不一致就停。创世自己被更新了，装好后从第 0 节按新版重跑（做完的会显示为复用）。
2. **备份仓库**（可和第 3 项并行）：清单是「新建」的，跑 `gh repo create 〈登录账号〉/flow-ledger-backup --private`，再 `L backup-init --remote https://github.com/〈登录账号〉/flow-ledger-backup`；选了「新建（旧备份归档）」的，在 `/home/box/flow-data/.backup-repo` 里把 `流程治理/` 用 git mv 移到 `_归档/流程治理-〈旧库ID前8位〉/` 再提交推送。失败就停下问。
3. **专职 bot**（可和第 2 项并行）：「新建」「补建」的用 CreateAgent 按 `templates/qa.md`、`templates/idea-critic.md` 全文建，建好读 profile.json 用 `H` 核对。平台会让它们各问候一句，不用管。
4. **定时任务**：清单里动作是「新建」的，按 routines.md 第 1–3 节的指令原文建（把〈bot ID〉换成自己的 ID），时间按清单；「复用」的不动，「不一致」的按清单的决定处理。
5. **写台账**：生成计划文件 `/home/box/flow-data/流程治理/runs/〈YYYYMMDD-HHMMSS〉-〈bot ID 前 8 位〉/genesis-plan.json`，内容只来自清单：
   ```json
   {"仓库": {"地址": "https://github.com/〈账号〉/flow-governance", "方式": "新建私有", "可见性": "私有", "tag": "〈版本标签〉", "提交号": "〈完整提交号〉"},
    "备份仓库": {"地址": "https://github.com/〈账号〉/flow-ledger-backup", "方式": "新建"},
    "库": {"方式": "新建"},
    "专职": [{"bot_id": "…", "名称": "专职·流程QA", "模板": "qa.md@〈版本标签〉"}],
    "收编": [{"bot_id": "…", "名称": "副官·记账", "模板": "deputy.md@〈版本标签〉", "类型": "副官", "所属项目": "记账", "库路径": "/home/box/flow-data/记账/ledger.db"}],
    "退役": [], "改已废弃": [],
    "定时任务": [{"名称": "流程治理·每日扫描", "时间": "每天 08:30"}],
    "skill": [{"名称": "flow-general", "动作": "补建"}],
    "用户确认": {"原话": "〈用户确认清单的原话〉", "时间": "〈时间〉"}}
   ```
   专职、收编的 `bot_id` 是第 3 项 CreateAgent 返回的或盘点里已有的 ID，执行时回填，不算清单外参数。
   版本标签和提交号从 `L where --project 流程治理` 第一行括号里的「仓库版本 〈标签〉 / 提交 〈前 12 位〉」取（前 12 位就够；不在 tag 上时标签是 `draft-〈提交号前 12 位〉`），或用 `git -C /home/box/flow-repo describe --tags --exact-match` 和 `git -C /home/box/flow-repo rev-parse HEAD`。收编的每一项都写齐类型、所属项目，副官还要写库路径（库必须已经存在），缺了 genesis 会按「专职 / 共用」处理或整单拒绝。然后跑 `L genesis --actor 〈你的 bot ID〉 --plan 〈计划文件〉`。它一个事务写完：meta（项目仓库、流程版本）、D-1、F-1、R-1、名册各行，**最后写你自己那一行**（参谋长、在用、库路径），再推备份、打印分类计数。这一行就是创世完成的标记，所以不拆开写、不把它留到检查之后。这一步自己做，不交给子代理。
   - **补录范围**（唯一定义处，J5）：只记 1 条 D 和 1 条 F。新建时 D-1 是「创世例外」（类型「版本」，含 tag、提交号、确认原话和时间、本次动作摘要），复用时是「创世（复用历史）」（含旧、新参谋长 bot ID）；F-1 是「仓库文件清单」（`git ls-tree` 的结果），复用时同一 tag 记过就不再记。R-1「共用 bot 不能开无上下文会话，项目隔离只靠派活单和自律」只在没有时记。补录理由：新建时「创世时 skill 规定」，复用时「接手时已存在」。
   - 创世时建的 bot 由 D-1 一并覆盖，不另记 D；创世不登记共享记忆里的偏好。
6. **检查**：第 5 项成功后才跑 `CHK run --project 流程治理 --governance --actor 〈你的 bot ID〉 --trigger 创世 --log`。
7. 结果是降级（演练时「克隆不在 tag 上」是预期的降级）：跑 `L degrade on --project 流程治理 --actor 〈你的 bot ID〉 --reason "〈终端输出里的降级原因〉"`。有发现：列进报告，不自己修。
8. 某步失败就停下报告，不猜、不绕。第 5 项之前失败的，重跑从第 0 节开始，做完的会在盘点里显示为复用（genesis 是一个事务，失败时什么都没写）。第 5 项已成功后（检查、降级、报告这几步）失败的，不重跑创世，只补做失败的那一步。

不自行分析或设计，清单以外的事一律不做。

## 5. 报告（固定格式）
1. 一行一项列出新建、复用、更新、补建、收编、退役、改已废弃和核对结果；失败、跳过、落后、设定不一致单独列。
2. 「台账写入」照抄 `L genesis` 打印的分类计数，不自己数；它的最后一行备份结果也照抄，是「备份：失败」的按 skill「flow-general」（通用流程，`/home/box/flow-repo/skills/general-flow/SKILL.md`）第 2 节「备份」处理。
3. 「检查脚本终端输出全文（检查日志 C-n）」：代码块，原样贴，不删减、不改写；可以在代码块前加一句导读，不能用摘要代替。
4. result.json 的路径（检查脚本终端输出最后一行「结果文件：…」）。

## 6. 创世之后
问：「你的第一个想法是什么？」用户给出想法后，按 skill「flow-chief-governance」（参谋长治理，`/home/box/flow-repo/skills/chief-of-staff-governance/SKILL.md`）第 7.1a 节「第一个副官交接」继续，本 skill 到此结束。
