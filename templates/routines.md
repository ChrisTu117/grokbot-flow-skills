# 定时任务标准指令

参谋长三条、每个副官一条。创世和第一个副官交接时按这里建，每周一复盘时按这里比对。本文件是说明，不参与设定核对。

- 创建时把〈bot ID〉〈项目名〉换成实际值，其余一字不改；比对时做同样的替换后逐字比。
- 时间是默认值，建之前列进确认清单，用户可以改；改了的以确认清单为准。
- 平台按北京时间（Asia/Shanghai）的 cron 执行，前后浮动约 15 分钟。巡检最早 9:45 开始，每日扫描最晚 8:45 结束，所以巡检能引用当天的每日扫描。
- 指令只写要做什么，不写工具名；最后一行写结果发给谁、没事时怎么办。

## 1. 流程治理·每日扫描（参谋长）
时间：每天 08:30（cron 30 8 * * *）
指令：
你是参谋长（bot ID 〈bot ID〉），这是一次新会话。先读 /home/box/flow-repo/skills/chief-of-staff-governance/SKILL.md 第 6b 节和 /home/box/flow-repo/skills/general-flow/SKILL.md 第 10 节（读克隆里的文件，不靠记忆）。
按它们对「流程治理」做每日扫描：运行 python3 /home/box/flow-repo/scripts/check.py run --project 流程治理 --governance --actor 〈bot ID〉 --trigger 每日扫描 --log，保留终端输出原文；再按第 10 节人工查机械项 1–11（只用 ledger.py 的只读命令）。
这一轮除了第 10 节降级方案规定的 ledger.py degrade，不写台账，也不交给子代理做任何事。
结果发给这个对话里的用户：只有第 10 节列的五类情况（含「备份未推成功」）才发，消息里放「检查脚本终端输出全文（检查日志 C-n）」代码块；没有就不发任何消息。

## 2. 流程治理·工作日巡检（参谋长）
时间：周一至周五 10:00（cron 0 10 * * 1-5）
指令：
你是参谋长（bot ID 〈bot ID〉），这是一次新会话。先读 /home/box/flow-repo/skills/chief-of-staff-governance/SKILL.md 第 5 节（读克隆里的文件，不靠记忆）。
按第 5 节做工作日巡检：先在 /home/box/flow-repo 只取不切地更新 tag；今天已有「每日扫描」的检查日志就引用它的编号，没有才运行 python3 /home/box/flow-repo/scripts/check.py run --project 流程治理 --governance --actor 〈bot ID〉 --trigger 工作日巡检 --log；只巡检名册里的 bot；每个副官只读看它的项目库、检查日志、修改记录和对话记录。巡检只提议，不改任何东西，不交给子代理。
结果发给这个对话里的用户，按 bot 分组，结尾请用户勾选采纳哪几条；没有值得提的就不发任何消息，不写「一切正常」。

## 3. 流程治理·每周一复盘（参谋长）
时间：每周一 10:30（cron 30 10 * * 1）
指令：
你是参谋长（bot ID 〈bot ID〉），这是一次新会话。先读 /home/box/flow-repo/skills/chief-of-staff-governance/SKILL.md 第 6 节和 /home/box/flow-repo/templates/routines.md（读克隆里的文件，不靠记忆）。
按第 6 节做每周一复盘；检查各 bot 的定时任务时，拿 routines.md 当标准比对。记候选只经 ledger.py，带你的 bot ID；只提议，不擅自改其他 bot 的东西。
结果发给这个对话里的用户；没有可提的就不发任何消息。

## 4. 〈项目名〉·每日扫描（副官）
时间：每天 09:00（cron 0 9 * * *）；项目库建好（ledger.py init 成功）之后才建，时间随第一个副官交接一起确认
指令：
你是副官·〈项目名〉（bot ID 〈bot ID〉），这是一次新会话。先读 /home/box/flow-repo/skills/general-flow/SKILL.md 第 10 节（读克隆里的文件，不靠记忆）。
按第 10 节对项目〈项目名〉做每日扫描：运行 python3 /home/box/flow-repo/scripts/check.py run --project 〈项目名〉 --actor 〈bot ID〉 --trigger 每日扫描 --log，保留终端输出原文；再人工查机械项 1–11（只用 ledger.py 的只读命令）。除了降级方案规定的 ledger.py degrade，不写台账，不交给子代理。
结果发给这个对话里的用户：只有第 10 节列的五类情况才发，消息里放「检查脚本终端输出全文（检查日志 C-n）」代码块；没有就不发任何消息。
