# 测试工装（压力测试、触发测试）

治理 skill 第 4 节要求改 skill 或模板时做压力测试和触发测试；本目录让参谋长每次都用同一套题、同一种跑法，结果能和上次逐题对比。

## 目录
- `pressure/scenarios.json`：压力题。每题有 `id`、`角色模板`（作答 bot 的设定正文）、`项目`、`先读`（先读哪份文件）、`补充`、`题面`（开放式，不给选项、不写规矩原话），以及评分用的 `依据`、`合格`、`不合格`。P1–P26 是各节规矩的题（P4、P5、P13 空号），C1–C10 是资料取用和秘密文件、改补充段、改造空档，B1–B3 是大变更，N1–N4 是摩擦记录、参谋长停摆告警、审查者保护、摩擦汇总。
- `trigger/cases.json`：触发题。`组`（A/B 治理，G 创世，F 通用，O 上手，N 无角色，K 大变更）、`skill`、`该触发`、`角色`、`请求`、`可接受`（N 组只许选这些）。
- `trigger/catalog.md`：skill 目录。四个流程 skill 的位置写成 `{{英文名}}`，出题时换成被测仓库里的 description 原文；其余是干扰项（本机其他 skill 的描述，固定不变，保证前后可比）。
- `run.py`：出题、作答、评分、对比。

## 一条命令
```
python3 /home/box/flow-repo/tests/run.py all --suite both --reps 3
```
- 被测的是 `run.py` 所在的那份仓库：草稿在工作目录里（如 `/home/box/flow-work-〈版本〉/tests/run.py`）就测草稿。
- 只跑一部分：`--suite pressure --only N1,N2 --reps 3`；无 skill 对照：`--mode without`（题面原样，不给 skill 和文件）。
- 结果目录默认 `/home/box/flow-data/流程治理/runs/tests/〈时间〉-〈提交号前 12 位〉/`：`manifest.json`（提交、tag、各 skill 和模板的规范化 hash、参数）、`in/`（题目全文）、`out/`（答案原文）、`judge/`（评分题和评分答案）、`marks.json`（人工改判，可选）、`summary.json`、`结果.md`。结果不进仓库。
- 中途被打断：对同一个目录再跑 `python3 tests/run.py run --out 〈目录〉`，已有答案的跳过。

## 作答怎么跑（平台限制）
- **有 `grok` 命令行时**（box 上一般有）：`run` 对每个任务起一个全新的无上下文进程：`GROK_MEMORY=0 grok -p 〈题目全文〉 --cwd 〈被测仓库或空目录〉 --sandbox strict --tools read_file --disallowed-tools search_tool,use_tool --max-turns 40 --no-auto-update --output-format plain`。只能读文件、不能写、不带记忆，默认 6 个并行，每个最长 15 分钟。带 skill 的题工作目录是被测仓库，触发题和无 skill 对照用空目录。
- **没有命令行时**：`run` 会列出还差哪些任务。参谋长逐个开**无上下文临时子任务**（不建 bot），把 `in/〈题〉.txt` 全文原样作为任务内容，不加别的话；子任务的回答原文存成 `out/〈题〉-r〈n〉.md`。一个任务一个子任务，不复用。存齐后接着跑 `judge` / `score`。

## 评分
- 触发题：`score` 自动判。读答案里的 JSON `read` 列表，按每题多数票统计，门槛是召回 ≥7/8、误触发 ≤1/8。
- 压力题：`judge` 为每份答案生成一道评分题（题面 + 合格/不合格标准 + 答案），评分答案的第一行是「合格」或「不合格」。评分题交给无上下文子任务做，跑法同上；`all` 会自动接着跑。**评分子任务只是初判**：参谋长必须逐份读答案核对，改判的写进 `marks.json`（如 `{"N1-with-r2": "不合格"}`），再跑一次 `score`。下一步动作违规也算不合格。
- 对比：`python3 tests/run.py compare 〈上次目录〉 〈这次目录〉`，列出合格数有变化的题。验收材料里附 `结果.md`、对比输出和 `manifest.json` 里的提交号。

## 加题
- 改到哪条规矩，就针对它加 3 道以上压力题。题面要叠压力（赶时间、沉没成本、用户或权威施压、疲劳、「这次情况特殊」），开放式，不给选项，不写规矩原话。`合格` 和 `不合格` 写成能对着答案逐条核的句子。
- 改了 description 的，给每个受影响 skill 加够 8 条该触发、8 条不该触发的题。
- 题目文件和 `run.py` 本身的改动跟着 skill 一起走第 4 节流程（`tests/` 不算大变更）。
