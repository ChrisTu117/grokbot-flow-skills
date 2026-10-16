# grokbot-flow-skills

参谋长流程 v0.0.1 的五个 skill 原文（逐字节，含 frontmatter）。

| Skill | 路径 | 原文地址 | 规范化 SHA-256 |
|---|---|---|---|
| 上手 | `skills/onboarding/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/onboarding/SKILL.md | `894d37319d2473e822a766aa16b491a8b875a556b281f011a9effa872eb5e123` |
| 创世 | `skills/genesis/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/genesis/SKILL.md | `28ae6ba221746d699f1f04d27bcd7df04ff4e39d43c22dcfb3e9b5f95d06d155` |
| 固定bot设定 | `skills/fixed-bot-settings/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/fixed-bot-settings/SKILL.md | `3ce492fa2d75e2d5a24acb8b5f5e70b5912e98c18eec4a1349a349aed5854ff0` |
| 参谋长治理 | `skills/chief-of-staff-governance/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/chief-of-staff-governance/SKILL.md | `ebf7d7554e9e5143128fef95a9504d4eae6713327d33a78a653b2f21aa94af69` |
| 通用流程 | `skills/general-flow/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/general-flow/SKILL.md | `7d9a1ae291c2c5787d96eb0ea99bfd18e3c65e2681105770e633b60dbca7a09d` |

## 计算哈希

去掉 frontmatter → 换行统一为 LF → 去掉每行行尾空白 → 去掉首尾空行 → SHA-256：

```
python3 build/hash.py skills/<slug>/SKILL.md
```
