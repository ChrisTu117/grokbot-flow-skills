# skill 目录

- 故障定性清单：Use before telling the user that something is broken on the platform side, out of your hands, or impossible. Walk through settings, usage limits, local docs and vendor docs first, and list what you checked.
- 新手引导（旧）：已停用，请勿使用
- chat-friction-review：Use for the scheduled weekday review of recent bot conversations: spot repeated user corrections, frustration, redo loops, unchecked links and blocked tools, and suggest categorized fixes. Say nothing when there is nothing worth raising.
- payout-compliance-check：Use before launching a paid feature in a new market: check whether the product may legally sell there and whether the payment provider will actually pay out to the seller's entity.
- 项目推进（旧）：已停用，请勿使用
{{flow-onboarding}}
- template-smoke-test：Use as the very first conversation after a bot template is installed, to confirm its skills loaded.
- secrets-register：Use whenever an API key, token or password is issued, moved, rotated or required for a deployment: note where it is stored (never the value itself) and which environment uses it.
- 长任务分段执行：开始任何耗时很长的实验、批处理或基准测试之前使用：先确认目的，再拆段执行、支持断点续跑、每段记下结论。
- sprite-sheet-delivery：Use when drawing small sprites or icons, or packaging art assets for a game build.
- iso-diagram：Draw detailed isometric SVG illustrations that explain a technical concept as a physical object (a machine, a gauge, a cabinet), with careful shading, a labeled card and gentle animation. Use whenever someone wants an explanatory figure for docs, a blog post or a landing page, or an interactive diagram showing how a system or algorithm works. Works as plain TypeScript/JS emitting SVG and HTML, or as a React component.
- skill-testing：Use when creating or editing a skill, or when checking that a skill behaves correctly before rolling it out.
- recurring-tasks：When the user wants something to happen on a schedule or on an event, such as a reminder, a digest, a watcher, "tell me when", or a change to an existing recurring task; read before creating or editing it.
{{flow-general}}
- 活动选题评审：在给用户列任何参赛或申报选题之前使用：按资格核对→评审标准打分→用户报名→开发提交→进度表的固定步骤逐项执行。
- debugging-checklist：Use when you hit a bug, a failing test or unexpected behavior, before proposing a fix.
- add-connector：Guide the user through connecting a new MCP connector: find it in the catalog, install it and sign in.
- export-bot-template：Package this bot's configuration as a shareable template. Use when the user wants to share or export the bot itself; not for giving teammates a shared copy they can chat with.
{{flow-chief-governance}}
- plan-before-coding：Use when you have requirements or a spec for a multi-step change and have not started editing code yet.
- calendar-helper：When the user talks about their calendar, meetings, availability, finding a time with others, booking an appointment or anything else about their schedule, read this before acting.
{{flow-genesis}}
- routine-cost-audit：Use for the weekly audit of every bot's scheduled tasks and of machine health: runs that are too frequent, too long, noisy when empty, dead or duplicated, plus memory and long-running processes. Silent when nothing to report.
- 新手引导（旧）：已停用，请勿使用
- idea-shortlist：Use before proposing or committing to an idea for a contest or grant: run the ordered screening gates (overlap with past entries, judge fit, side prizes, demo feasibility) and score each candidate.
- send-as-user：When the user asks you to write, draft, reply to or send an email or message in their name on another platform (email, Slack, another chat app).
- save-as-skill：When you notice a reusable multi-step procedure worth keeping, or the user asks you to save, edit or remove a skill.
- source-control：When work involves GitHub or another code host: reading or changing repositories, pull requests, issues or CI with the built-in tools, deciding between those and a cloud agent, or a tool fails for permission or connection reasons.
- release-acceptance：Use when doing the final acceptance pass on a live deployment before it ships.
- no-connector-fallback：When a service the user needs has no connector, a connector must be installed or re-authenticated, a command-line tool on the box needs a login, or a browser flow stops at a sign-in page.
