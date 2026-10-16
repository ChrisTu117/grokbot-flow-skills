# grokbot-flow-skills

参谋长流程 v0.0.1 的五个 skill 原文（逐字节，含 frontmatter）。

| Skill | 路径 | 原文地址 | 规范化 SHA-256 |
|---|---|---|---|
| 上手 | `skills/onboarding/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/onboarding/SKILL.md | `894d37319d2473e822a766aa16b491a8b875a556b281f011a9effa872eb5e123` |
| 创世 | `skills/genesis/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/genesis/SKILL.md | `f298910ae78171c3b19782d37351bad3171adb6a9fc2dd1df0acfad76d2d43ff` |
| 固定bot设定 | `skills/fixed-bot-settings/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/fixed-bot-settings/SKILL.md | `7ff3de516a4b36dbe17b0ff569064a6b5942edb1ee355ed5bc004a2708fd1a4f` |
| 参谋长治理 | `skills/chief-of-staff-governance/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/chief-of-staff-governance/SKILL.md | `e5132f192d41b19d79e9e803074cba91452fd96e60688ef07b74f1ba7ddd5234` |
| 通用流程 | `skills/general-flow/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/general-flow/SKILL.md | `7d9a1ae291c2c5787d96eb0ea99bfd18e3c65e2681105770e633b60dbca7a09d` |

## 计算哈希

去掉 frontmatter → 换行统一为 LF → 去掉每行行尾空白 → 去掉首尾空行 → SHA-256：

```
python3 build/hash.py skills/<slug>/SKILL.md
```
