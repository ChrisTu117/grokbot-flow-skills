# bot 模板

一个文件一个模板，文件里只放设定正文，建 bot 时整段贴进描述。本页和 `routines.md` 是说明，不参与设定核对。

| 模板 | 文件 | 名称格式 | 类型 | 必要应用 | 可选应用 | 定时任务 |
|---|---|---|---|---|---|---|
| 参谋长 | `chief-of-staff.md` | 参谋长 | 参谋长 | GitHub（bot 电脑命令行授权：本项目仓库 + 备份仓库 flow-ledger-backup） | Slack（巡检和复盘通知） | 三个，指令和时间见 `routines.md` 第 1–3 节 |
| 副官 | `deputy.md` | 副官·〈项目名〉 | 副官 | 无（台账在本机 `/home/box/flow-data/〈项目名〉/ledger.db`，经 `scripts/ledger.py` 写） | 按项目：GitHub（写代码）、Cloudflare（部署）、Figma（设计）、Slack（通知） | 一个，建好项目库后自己建，见 `routines.md` 第 4 节 |
| 专职·流程QA | `qa.md` | 专职·流程QA | 专职，共用、不绑项目 | 无。台账不直接读，只看派活单附的材料；派活单写明要它查时，用 `python3 /home/box/flow-repo/scripts/ledger.py show`（只读） | 无 | 无 |
| 专职·想法挑刺 | `idea-critic.md` | 专职·想法挑刺 | 专职，共用、不绑项目 | 无（只用联网搜索） | 无 | 无 |
| 专职 bot 通用规矩 | `specialist-common.md` | — | 不单独建 bot | — | — | — |

- **占位**：`deputy.md` 里的「〈项目名〉」建 bot 时换成实际项目名。核对时只做这一处替换。
- **项目专有补充**：`deputy.md` 最后一行是「【项目专有补充】」。这一行之后可以接本项目的领域知识、语气、用户偏好和项目专有规矩，新建的副官留空。核对只比到这一行为止，补充段归项目所有，改动由副官记进本项目 D 表（中等变更），用户确认。
- **首次运行**：平台建好 bot 后会自动给它一轮首次运行。三个专职模板和 `specialist-common.md` 都写了「只说一句、不复述个人信息」；副官只说一句、等参谋长交接单；参谋长问候一句后直接执行创世。
- **专职 bot 通用规矩**：参谋长新写专职 bot 时放在设定正文末尾；从模板库导入的专职 bot，经用户批准后由参谋长追加到它的设定正文末尾。模板库导入的保留原名。
- **专职·想法挑刺**：用户个人情况放共享记忆，不写进设定正文。它和无上下文红队评审不合并：想法挑刺要用户上下文并长期存在；红队评审由发起方每次开无上下文临时子任务，不建 bot。
- **副官和参谋长**：设定正文只写定位和启动规矩，规矩在 skill「flow-general」（通用流程，`/home/box/flow-repo/skills/general-flow/SKILL.md`）第 0 节「副官守则」，参谋长另加 skill「flow-chief-governance」（参谋长治理，`/home/box/flow-repo/skills/chief-of-staff-governance/SKILL.md`）第 0 节「参谋长守则」。专职 bot 的设定正文就是它的全部核心规矩。
- **名册**：所有 bot 登记在流程治理库（`/home/box/flow-data/流程治理/ledger.db`）的 B 表；建 bot、名册登记、升级见 skill「flow-chief-governance」（参谋长治理，`/home/box/flow-repo/skills/chief-of-staff-governance/SKILL.md`）第 3 节（列定义）、第 7 节（建 bot、第 7.3 节登记）、第 4c 节（升级）。
