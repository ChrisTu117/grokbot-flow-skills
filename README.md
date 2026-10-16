# grokbot-flow-skills

参谋长流程 v0.0.1 的五个 skill 原文（逐字节，含 frontmatter）。

| Skill | 路径 | 原文地址 | 规范化 SHA-256 |
|---|---|---|---|
| 上手 | `skills/onboarding/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/onboarding/SKILL.md | `58675a39212752b11a2eca0fbac95efd60423bb64786d9b9aaf1b6a35f10b65c` |
| 创世 | `skills/genesis/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/genesis/SKILL.md | `b910f89d9fee11cdfc0dd208f8865099c8d79f689aadad6fd6c85d2c2cb81066` |
| 固定bot设定 | `skills/fixed-bot-settings/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/fixed-bot-settings/SKILL.md | `c9b5ba313d6e1f7d5061d8a4b8998b5a6e49ffbe16baee7068705c92483dd808` |
| 参谋长治理 | `skills/chief-of-staff-governance/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/chief-of-staff-governance/SKILL.md | `fca8a88c8fde0e4f2f030c62ba877736a5507c69b188430a047886dba0b5f069` |
| 通用流程 | `skills/general-flow/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/general-flow/SKILL.md | `7d9a1ae291c2c5787d96eb0ea99bfd18e3c65e2681105770e633b60dbca7a09d` |

## 计算哈希

去掉 frontmatter → 换行统一为 LF → 去掉每行行尾空白 → 去掉首尾空行 → SHA-256：

```
python3 build/hash.py skills/<slug>/SKILL.md
```
