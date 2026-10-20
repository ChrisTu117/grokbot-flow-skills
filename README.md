# grokbot-flow-skills

参谋长流程 v0.0.1 的五个 skill 原文（逐字节，含 frontmatter）和检查脚本。

| Skill | 路径 | 原文地址 | 规范化 SHA-256 |
|---|---|---|---|
| 上手 | `skills/onboarding/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/onboarding/SKILL.md | `ebaa2184176ad6046f87fbb89dd1337f12d94d6b4d4c9c0ce3407eca0b4ea724` |
| 创世 | `skills/genesis/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/genesis/SKILL.md | `1d5d9b08a19011f2f5f6c3e93e965c7ff0a61eaba1f0decb0e705441e19aec73` |
| 固定bot设定 | `skills/fixed-bot-settings/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/fixed-bot-settings/SKILL.md | `1967670bfceabca5b9a4686c184b0b7f72c2647c202c6afba1b5aa670982d650` |
| 参谋长治理 | `skills/chief-of-staff-governance/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/chief-of-staff-governance/SKILL.md | `b72b9df81daa8973c6bdb84bdea837f4790ac6ad8b37e989f06e9fecee7cb11a` |
| 通用流程 | `skills/general-flow/SKILL.md` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/skills/general-flow/SKILL.md | `c86c52a2c49a2ccc9768a19b4127c78ec456fa279dbac333e67d8212709172e0` |
| 检查脚本 | `scripts/check.py` | https://raw.githubusercontent.com/ChrisTu117/grokbot-flow-skills/main/scripts/check.py | `7f3ebfcf4173e9abcb2cd9501f80bd61f5fe68f639cc68b33616f3499a8b7b7a` |

## 计算哈希

规范化 v2：frontmatter 只取 name、description 两个值，按固定两行重写（没有 frontmatter 的文件不加）；正文换行统一为 LF → 去掉每行行尾空白 → 去掉首尾空行 → SHA-256：

```
python3 build/hash.py skills/<slug>/SKILL.md
```
