# grokbot-flow-skills

参谋长流程 v0.0.1 的五个 skill 原文（逐字节，含 frontmatter）。

| Skill | 路径 | 原文地址 | 规范化 SHA-256 |
|---|---|---|---|
| 上手 | `skills/onboarding/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/onboarding/SKILL.md | `38559bb0c8bb19b2782aa67e5c1fdc7c5f054d4f2efbb5abd3c073f028c19b89` |
| 创世 | `skills/genesis/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/genesis/SKILL.md | `4c8e92757575d4f1749a6762c2b0c9603b70ea75303eec2da8f3fd9114d3b386` |
| 固定bot设定 | `skills/fixed-bot-settings/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/fixed-bot-settings/SKILL.md | `f14f7d183807f37ed7bf32a50a4ca1214f541b22c765b863356a9f98479e8123` |
| 参谋长治理 | `skills/chief-of-staff-governance/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/chief-of-staff-governance/SKILL.md | `e8fa9aa63589688b20d26eea7541bff18e1e1c03efd0f0836f499392e72b130e` |
| 通用流程 | `skills/general-flow/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/general-flow/SKILL.md | `7d9a1ae291c2c5787d96eb0ea99bfd18e3c65e2681105770e633b60dbca7a09d` |

## 计算哈希

去掉 frontmatter → 换行统一为 LF → 去掉每行行尾空白 → 去掉首尾空行 → SHA-256：

```
python3 build/hash.py skills/<slug>/SKILL.md
```
