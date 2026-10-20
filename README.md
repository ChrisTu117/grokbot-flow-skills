# grokbot-flow-skills

参谋长流程的维护中心：skill、bot 模板、检查脚本都在这里。版本和修改记录全在 git：整个仓库一个版本号，用带说明的 tag `vX.Y.Z`，没打 tag 的提交不算发布。

| 目录 | 内容 |
|---|---|
| `skills/<slug>/SKILL.md` | 四个 skill：上手 `onboarding`、创世 `genesis`、参谋长治理 `chief-of-staff-governance`、通用流程 `general-flow` |
| `templates/` | bot 模板，一个文件一个模板，只放设定正文；说明见 `templates/README.md` |
| `scripts/check.py` | 检查脚本（导出完整性；本机对仓库比对） |
| `build/hash.py` | 规范化哈希，检查脚本直接调用 |

## 怎么装

参谋长把本仓库克隆到 `/home/box/flow-repo`，切到最新 tag，再从克隆装 skill、建 bot、跑脚本。首次引导写在 `templates/chief-of-staff.md`，其余由 skill「创世」完成。细则见 skill「参谋长治理」第 1、4 节。

## 计算哈希

规范化 v2：frontmatter 只取 name、description 两个值，按固定两行重写（没有 frontmatter 的文件不加）；正文换行统一为 LF → 去掉每行行尾空白 → 去掉首尾空行 → SHA-256。哈希不登记在任何地方，要核对就现算：

```
python3 build/hash.py skills/<slug>/SKILL.md
python3 scripts/check.py run --governance    # 本机 skill 与克隆比、落后清单
python3 scripts/check.py selftest
```
