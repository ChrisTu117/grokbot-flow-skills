#!/usr/bin/env python3
"""检查脚本 v0.0.1（草稿 3）——纯标准库 Python 3。只做两件事：导出完整性（含编号缺号、行数不减）和治理哈希核对。
通用流程第 10 节机械项 1–11 不归本脚本，由人工按清单检查。

用法：
  python3 check.py run --export-dir 导出目录 [--agents-dir DIR] [--workflows-dir DIR] [--prev 上次结果.json] [--out 结果.json]
  python3 check.py escape 原文文件            # 输出写入 Notion 前的转义文本（stdout）
  python3 check.py verify-text --original 原文文件 --export 导出文件 --page-id ID --field 字段名
                                              # 写入后读回核对：view/fetch 导出还原后与原文哈希比
  python3 check.py selftest [--fixtures DIR]  # 单测 demarkdown2 / escape_md / 解析

导出目录（bot 每次巡检建一个带时间戳的子目录）：
  manifest.json  {"project": "流程治理", "exported_at": "...",
                  "tables": [{"role": "B", "name": "bot 名册", "view_url": "view://..."} , ...],
                  "sql": [{"role": "B", "file": "B-sql.txt"}]}        # sql 可省
  <role>-db.txt                    该数据库的 notion-fetch 结果（用来确认所用视图不带筛选）
  <role>-p1.txt, <role>-p2.txt ...   每页一个文件：CallDynamicTool(write_to_file) 的原样结果
  role：F D R S P A（项目表）、T 模板表、B bot 名册、K skill 维护表、J 脚本维护表

哈希规范化与仓库 build/hash.py 完全一致（规范化 v2：frontmatter 只保留 name、description 的值并改写成固定两行，LF、行尾空白、首尾空行，不做任何替换）。
结论分三类：发现（确定不一致）、降级（导出不完整或无法判定，不算不一致）、正常。
"""
import argparse, datetime, glob, hashlib, json, os, re, sys

VERSION = "v0.0.1-draft.3"
ID_RE = re.compile(r"([0-9a-f]{32})")
CURRENT_STATES = {"在用", "暂停", "退役"}          # 当前版本行可能的状态（模板/skill/脚本表只有在用）

# ---------- 文本工具（可单测） ----------
_ESC_CHARS = r"\*_`[]<>#~|"
_ESC_RE = re.compile("([" + re.escape(_ESC_CHARS) + "])")

def escape_md(text: str) -> str:
    """写入 Notion 前转义：\\ * _ ` [ ] < > # ~ | 前加反斜杠。换行保持原样。"""
    return _ESC_RE.sub(r"\\\1", text)

# 单遍扫描：\x → x；<br> → 换行；[文字](http…) → 文字（Notion 自动加的链接，文字内部递归处理）
_TOK = re.compile(r"\\(.)|<br>|\[((?:\\.|[^\]\\])*)\]\((https?://[^)]*)\)", re.S)

def demarkdown2(v: str) -> str:
    """把 view/fetch 返回的 markdown 化富文本还原成写入前的原文（前提：写入时做过 escape_md）。"""
    def rep(m):
        if m.group(1) is not None:
            return m.group(1)
        if m.group(0) == "<br>":
            return "\n"
        return demarkdown2(m.group(2))
    return _TOK.sub(rep, v)

def suspicious_unescaped(v: str) -> bool:
    """还原前的值里出现未转义的 markdown 记号 → 原文写入时可能没转义，存储已被改写，不可判定。
    只看明显记号：未转义的 * _ ` ~ #（链接、<br> 是 Notion 渲染产物，已由 demarkdown2 处理）。"""
    s = _TOK.sub(lambda m: "" if m.group(1) is not None else ("\n" if m.group(0) == "<br>" else m.group(2)), v)
    return bool(re.search(r"[*`~]", s))

# 规范化 v2：与仓库 build/hash.py 逐字同一实现（frontmatter 只计 name、description 的值）
KEYS = ("name", "description")

class FrontmatterError(ValueError):
    pass

def _scalar(first: str, cont: list) -> str:
    """first：键冒号后的文本（已去首尾空白）；cont：属于该键的后续行（原样）。"""
    if first in (">+", "|+"):
        raise FrontmatterError("保留尾部换行（+）写法不支持")
    if first in (">", ">-", "|", "|-"):
        ind = [len(l) - len(l.lstrip(" ")) for l in cont if l.strip()]
        if not ind:
            return ""
        n = min(ind)
        body = [l[n:] if l.strip() else "" for l in cont]
        while body and body[-1] == "":
            body.pop()
        if first[0] == "|":
            s = "\n".join(body)
        else:  # 折叠：相邻非空行用空格连接，空行变换行；更深缩进的行保留换行
            s, prev_more = "", False
            for i, l in enumerate(body):
                more = l.startswith((" ", "\t"))
                if i == 0:
                    s = l
                elif l == "":
                    s += "\n"
                elif s.endswith("\n") or more or prev_more:
                    s += ("" if s.endswith("\n") else "\n") + l
                else:
                    s += " " + l
                prev_more = more
        return s if first.endswith("-") else s + "\n"
    if cont and any(l.strip() for l in cont) and first[:1] in ("'", '"'):
        raise FrontmatterError("多行引号标量不支持")
    if first[:1] == "'":
        if not (len(first) >= 2 and first.endswith("'")):
            raise FrontmatterError("单引号未闭合")
        return first[1:-1].replace("''", "'")
    if first[:1] == '"':
        if not (len(first) >= 2 and first.endswith('"')) or "\\" in first:
            raise FrontmatterError("双引号未闭合或含转义（不支持）")
        return first[1:-1]
    if first[:1] in ("[", "{", "&", "*", "!", "%", "@", "`"):
        raise FrontmatterError("不支持的 YAML 写法")
    parts = [first] + [l.strip() for l in cont]  # 普通多行：去缩进，用空格连接（空行→换行）
    s = ""
    for p in parts:
        if p == "":
            s += "\n"
        elif s == "" or s.endswith("\n"):
            s += p
        else:
            s += " " + p
    return s.strip(" ")

def _frontmatter(lines: list) -> dict:
    vals, i = {}, 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:(.*)$", lines[i])
        if not m:
            if lines[i].strip() == "" or lines[i].lstrip().startswith("#"):
                i += 1; continue
            raise FrontmatterError(f"frontmatter 第 {i + 2} 行无法解析")
        key, first = m.group(1), m.group(2).strip()
        j = i + 1
        while j < len(lines) and (lines[j].startswith((" ", "\t")) or lines[j].strip() == ""):
            j += 1
        if key in KEYS:
            if key in vals:
                raise FrontmatterError(f"{key} 重复")
            if " #" in first and first[:1] not in ("'", '"'):
                first = first.split(" #", 1)[0].rstrip()
            vals[key] = _scalar(first, lines[i + 1:j])
        i = j
    for k in KEYS:
        if k not in vals:
            raise FrontmatterError(f"frontmatter 缺 {k}")
    return vals

def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                v = _frontmatter(lines[1:i])
                head = [f"{k}: " + v[k].replace("\n", "\\n") for k in KEYS] + ["---"]
                lines = head + lines[i + 1:]
                break
    return "\n".join(l.rstrip() for l in lines).strip("\n")

def norm_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()

def file_norm_hash(path: str) -> str:
    with open(path, encoding="utf-8-sig") as f:
        return norm_hash(f.read())

def page_id(url_or_id: str):
    m = ID_RE.search((url_or_id or "").replace("-", ""))
    return m.group(1) if m else None

# ---------- 导出文件解析 ----------
def load_export(path: str) -> dict:
    """兼容有/无首尾包裹标记：取第一个 { 到最后一个 }。"""
    with open(path, encoding="utf-8") as f:
        s = f.read()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < i:
        raise ValueError("文件里没有 JSON")
    return json.loads(s[i:j + 1])

def fetch_properties(path: str) -> dict:
    """notion-fetch 单页结果 → 属性字典。"""
    t = load_export(path)["text"]
    return json.loads(t[t.index("<properties>") + 12: t.index("</properties>")])

def page_no(path):
    m = re.search(r"-p(\d+)\.txt$", path)
    return int(m.group(1)) if m else 10**9

def read_table(export_dir: str, role: str) -> dict:
    """读一张表的全部分页，检查完整性。返回 {rows, pages, complete, issues}。"""
    files = sorted(glob.glob(os.path.join(export_dir, f"{role}-p*.txt")), key=page_no)
    out = {"pages": len(files), "rows": [], "complete": False, "issues": []}
    if not files:
        out["issues"].append("没有导出文件")
        return out
    if [page_no(f) for f in files] != list(range(1, len(files) + 1)):
        out["issues"].append("页号不连续：" + ",".join(os.path.basename(f) for f in files))
    seen, prev_cursor, dups = {}, None, []
    for n, f in enumerate(files, 1):
        try:
            j = load_export(f)
        except Exception as e:
            out["issues"].append(f"第{n}页解析失败：{e}")
            return out
        if "error" in j:
            out["issues"].append(f"第{n}页是错误返回：{j['error'].get('code')}")
            return out
        if "results" not in j or "has_more" not in j:
            out["issues"].append(f"第{n}页缺 results/has_more（不是 view 模式结果？）")
            return out
        rows = j["results"]
        if prev_cursor is not None:      # 实测：next_cursor 末尾是下一页第一行的 id
            first = page_id(rows[0]["url"]) if rows else None
            cur_id = page_id(prev_cursor.split(":")[-1])
            if first != cur_id:
                out["issues"].append(f"第{n}页首行与上一页 next_cursor 不衔接")
        for r in rows:
            pid = page_id(r.get("url", ""))
            if pid is None:
                out["issues"].append(f"第{n}页有行缺 url")
                continue
            if pid in seen:
                dups.append((pid, seen[pid], n))
                continue
            seen[pid] = n
            r["_id"] = pid
            out["rows"].append(r)
        last = n == len(files)
        if last and j["has_more"]:
            out["issues"].append("最后一页 has_more=true，没翻完")
        if not last and not (j["has_more"] and j.get("next_cursor")):
            out["issues"].append(f"第{n}页 has_more=false 或无 next_cursor，但后面还有页")
        prev_cursor = j.get("next_cursor")
    if dups:
        out["issues"].append(f"页间重复 {len(dups)} 行（如 {dups[0][0]}，第{dups[0][1]}页与第{dups[0][2]}页）")
    out["complete"] = not out["issues"]
    return out

def view_filter_issue(export_dir, role, view_url):
    """<role>-db.txt 是该数据库的 notion-fetch 结果；确认所用视图不带筛选。返回问题字符串或 None。"""
    f = os.path.join(export_dir, f"{role}-db.txt")
    if not os.path.exists(f):
        return "缺数据库结构文件，无法确认所用视图不带筛选"
    if not view_url:
        return "manifest 没写所用视图"
    try:
        t = load_export(f).get("text", "")
    except Exception as e:
        return f"数据库结构文件解析失败：{e}"
    vid = view_url.replace("view://", "").strip("{}")
    m = re.search(r'<view url="\{\{view://' + re.escape(vid) + r'\}\}">\n(\{.*?\})\n</view>', t, re.S)
    if not m:
        return "数据库结构里找不到所用视图"
    v = json.loads(m.group(1))
    k = filter_key(v)
    if k:
        return f"所用视图「{v.get('name')}」带筛选（{k}），不是全量"
    return None

def filter_key(obj, path=""):
    """视图定义里任何键名含 filter（不分大小写）且值非空，就返回该键路径；没有返回 None。"""
    if isinstance(obj, dict):
        for k, val in obj.items():
            p = f"{path}.{k}" if path else k
            if "filter" in k.lower() and val not in (None, "", [], {}, False):
                return p
            r = filter_key(val, p)
            if r:
                return r
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            r = filter_key(val, f"{path}[{i}]")
            if r:
                return r
    return None

def numbering_gaps(rows, prefix):
    nums = sorted(int(m.group(1)) for r in rows
                  for m in [re.fullmatch(prefix + r"-(\d+)", str(r.get("编号", "")).strip())] if m)
    if not nums:
        return []
    return [f"{prefix}-{i}" for i in range(1, nums[-1] + 1) if i not in set(nums)]

# ---------- 本机当前值 ----------
def local_skills(workflows_dir):
    """frontmatter name → [(路径, 规范化哈希)]"""
    res = {}
    for p in glob.glob(os.path.join(workflows_dir, "*", "SKILL.md")):
        try:
            with open(p, encoding="utf-8-sig") as f:
                s = f.read()
        except OSError:
            continue
        m = re.search(r"^name:\s*(.+?)\s*$", s.split("\n---", 1)[0], re.M)
        if m:
            try:
                h = norm_hash(s)
            except FrontmatterError as e:
                h = f"frontmatter 无法解析：{e}"
            res.setdefault(m.group(1).strip().strip("'\""), []).append((p, h))
    return res

def agent_description(agents_dir, bot_id):
    p = os.path.join(agents_dir, bot_id, "profile.json")
    if not os.path.isdir(os.path.join(agents_dir, bot_id)):
        return None, "bot 目录不存在"
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f).get("description"), None
    except Exception as e:
        return None, f"读不到 profile.json：{e}"

# ---------- 检查 ----------
class Report:
    def __init__(self):
        self.findings, self.degraded, self.ok = [], [], []
    def find(self, kind, table, obj, detail):
        self.findings.append({"类型": kind, "表": table, "对象": obj, "详情": detail})
    def degrade(self, table, obj, reason):
        self.degraded.append({"表": table, "对象": obj, "原因": reason})
    def good(self, table, obj, detail):
        self.ok.append({"表": table, "对象": obj, "详情": detail})

def current_rows(rows, key):
    by = {}
    for r in rows:
        if str(r.get("状态", "")).strip() in CURRENT_STATES:
            by.setdefault(str(r.get(key, "")).strip(), []).append(r)
    return by

def check_text_integrity(rep, table, obj, row, field):
    """登记的全文（view 还原）与登记哈希是否一致。不一致或可疑一律降级，不判不一致。"""
    v, h = row.get(field), str(row.get("内容哈希", "")).strip()
    if not v:
        rep.degrade(table, obj, f"{field} 为空")
        return
    if re.fullmatch(r"\s*(见|https?://)\S*.*", v) and len(v) < 200 and "notion" in v:
        rep.degrade(table, obj, f"{field} 是子页面链接，脚本不跟读")
        return
    restored = demarkdown2(v)
    if norm_hash(restored) == h:
        rep.good(table, obj, f"{field} 还原后哈希与登记一致")
    elif suspicious_unescaped(v):
        rep.degrade(table, obj, f"{field} 有未转义 markdown 记号，写入时可能没转义，无法还原判定")
    else:
        rep.degrade(table, obj, f"{field} 还原后哈希 {norm_hash(restored)[:12]} ≠ 登记 {h[:12]}，无法判定（可走 SQL 抽查）")

def check_sql(rep, export_dir, manifest, tables):
    """可选：SQL 抽查文件（SELECT url, 设定正文, 内容哈希 …），原文无需还原，直接比。"""
    for s in manifest.get("sql", []):
        role, f = s.get("role"), os.path.join(export_dir, s.get("file", ""))
        try:
            j = load_export(f)
        except Exception as e:
            rep.degrade(role, "SQL 抽查", f"文件读不到：{e}")
            continue
        if "error" in j:
            rep.degrade(role, "SQL 抽查", f"SQL 不可用（{j['error'].get('code')}），本次未抽查")
            continue
        field = {"B": "设定正文", "T": "设定正文"}.get(role)
        for r in j.get("results", []):
            v, h = r.get(field), str(r.get("内容哈希", "")).strip()
            if v is None or not h:
                continue
            obj = r.get("编号") or page_id(r.get("url", ""))
            if norm_hash(v) == h:
                rep.good(role, obj, "SQL 原文哈希与登记一致")
            else:
                rep.find("登记原文与哈希不符", role, obj, f"SQL 原文 {norm_hash(v)[:12]} ≠ 登记 {h[:12]}")

def run(args):
    ed = args.export_dir
    manifest = json.load(open(os.path.join(ed, "manifest.json"), encoding="utf-8"))
    rep, tables = Report(), {}
    for t in manifest["tables"]:
        role = t["role"]
        info = read_table(ed, role)
        tables[role] = {"名称": t.get("name"), "视图": t.get("view_url"), "行数": len(info["rows"]),
                        "页数": info["pages"], "完整": info["complete"], "问题": info["issues"]}
        vi = None if args.skip_view_check else view_filter_issue(ed, role, t.get("view_url"))
        if vi:
            info["issues"].append(vi)
            info["complete"] = False
        tables[role]["完整"], tables[role]["问题"] = info["complete"], info["issues"]
        if not info["complete"]:
            rep.degrade(role, t.get("name"), "导出不完整：" + "；".join(info["issues"]))
        prefix = {"F": "F", "D": "D", "R": "R", "S": "S", "P": "P", "A": "A",
                  "T": "T", "B": "B", "K": "K", "J": "J"}.get(role)
        gaps = numbering_gaps(info["rows"], prefix) if info["complete"] else []
        if gaps:
            rep.find("编号缺号", role, t.get("name"), "缺 " + ",".join(gaps[:20]))
        tables[role]["_rows"] = info["rows"]
    # 行数单调不减
    if args.prev and os.path.exists(args.prev):
        prev = json.load(open(args.prev, encoding="utf-8")).get("表", {})
        for role, t in tables.items():
            p = prev.get(role, {})
            if t["完整"] and p.get("完整") and t["行数"] < p.get("行数", 0):
                rep.find("行数减少", role, t["名称"], f"{p['行数']} → {t['行数']}")
    skills = local_skills(args.workflows_dir)
    # B bot 名册
    b = tables.get("B")
    if b and b["完整"]:
        for bid, rs in current_rows(b["_rows"], "bot ID").items():
            obj = f"{rs[0].get('名称')}（{bid}）"
            if len(rs) > 1:
                rep.find("多行当前版本", "B", obj, ",".join(r.get("编号", "") for r in rs))
                continue
            r = rs[0]
            check_text_integrity(rep, "B", obj + " " + str(r.get("编号")), r, "设定正文")
            desc, err = agent_description(args.agents_dir, bid)
            if err:
                (rep.find if "不存在" in err else rep.degrade)(*(("名册有而平台没有", "B", obj, err) if "不存在" in err else ("B", obj, err)))
                continue
            cur, reg = norm_hash(desc or ""), str(r.get("内容哈希", "")).strip()
            if cur == reg:
                rep.good("B", obj, "当前设定与在用行哈希一致")
            else:
                rep.find("设定正文不一致", "B", obj, f"当前 {cur[:12]} ≠ 在用行 {reg[:12]}（{r.get('编号')}）")
    # T 模板表
    t = tables.get("T")
    if t and t["完整"]:
        for name, rs in current_rows(t["_rows"], "模板名").items():
            if len(rs) > 1:
                rep.find("多行当前版本", "T", name, ",".join(r.get("编号", "") for r in rs))
                continue
            check_text_integrity(rep, "T", f"{name} {rs[0].get('编号')}", rs[0], "设定正文")
    # K skill 维护表：比本机 skill 规范化哈希（全文在行页面正文/附件，不在属性里，不还原）
    k = tables.get("K")
    if k and k["完整"]:
        for name, rs in current_rows(k["_rows"], "skill 名称").items():
            if len(rs) > 1:
                rep.find("多行当前版本", "K", name, ",".join(r.get("编号", "") for r in rs))
                continue
            reg = str(rs[0].get("内容哈希", "")).strip()
            loc = skills.get(name, [])
            if not loc:
                rep.find("本机缺 skill", "K", name, "workflows 下没有 frontmatter name 为该名的 SKILL.md")
            elif len(loc) > 1:
                rep.find("本机同名 skill 多份", "K", name, "；".join(p for p, _ in loc))
            elif loc[0][1].startswith("frontmatter"):
                rep.find("skill frontmatter 无法解析", "K", name, f"{loc[0][0]}：{loc[0][1]}")
            elif loc[0][1] == reg:
                rep.good("K", name, f"本机哈希与在用行一致 {reg[:12]}")
            else:
                rep.find("skill 不一致", "K", name, f"本机 {loc[0][1][:12]} ≠ 在用行 {reg[:12]}（{rs[0].get('编号')}）")
    # J 脚本维护表：比本脚本自身
    j = tables.get("J")
    if j and j["完整"]:
        me = file_norm_hash(os.path.abspath(__file__))
        rs = current_rows(j["_rows"], "脚本名称").get("检查脚本", [])
        if not rs:
            rep.degrade("J", "检查脚本", "脚本维护表没有检查脚本在用行")
        elif len(rs) > 1:
            rep.find("多行当前版本", "J", "检查脚本", ",".join(r.get("编号", "") for r in rs))
        elif not re.fullmatch(r"[0-9a-f]{64}", str(rs[0].get("内容哈希", "")).strip()):
            rep.degrade("J", "检查脚本", f"在用行内容哈希不是有效哈希（{rs[0].get('内容哈希')}），脚本未登记")
        elif rs[0]["内容哈希"].strip() == me:
            rep.good("J", "检查脚本", f"本脚本哈希与在用行一致 {me[:12]}")
        else:
            rep.find("脚本不一致", "J", "检查脚本", f"本脚本 {me[:12]} ≠ 在用行 {rs[0]['内容哈希'][:12]}")
    check_sql(rep, ed, manifest, tables)
    for t in tables.values():
        t.pop("_rows", None)
    status = "降级" if rep.degraded else ("有发现" if rep.findings else "正常")
    result = {"脚本": "检查脚本", "版本": VERSION, "脚本哈希": file_norm_hash(os.path.abspath(__file__)),
              "运行时间": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
              "导出目录": os.path.abspath(ed), "项目": manifest.get("project"), "状态": status,
              "覆盖范围": "导出完整性、编号连续、行数不减、治理哈希比对（参谋长治理第 5 节第 2 项）",
              "人工检查项": "通用流程第 10 节机械项 1–11 不归本脚本，由人工按清单检查（不算降级）",
              "表": tables, "发现": rep.findings, "降级": rep.degraded, "正常项数": len(rep.ok), "正常项": rep.ok}
    lines = [f"检查脚本 {VERSION}：{status}。{len(tables)} 张表，"
             f"{sum(t['行数'] for t in tables.values())} 行；发现 {len(rep.findings)} 条，降级 {len(rep.degraded)} 条，正常 {len(rep.ok)} 项。"]
    lines += [f"- 发现｜{x['表']}｜{x['对象']}｜{x['类型']}：{x['详情']}" for x in rep.findings]
    lines += [f"- 降级｜{x['表']}｜{x['对象']}：{x['原因']}" for x in rep.degraded]
    result["摘要"] = "\n".join(lines)
    out = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(out)
    print(result["摘要"])
    return {"正常": 0, "有发现": 1, "降级": 2}[status]

def cmd_escape(args):
    sys.stdout.write(escape_md(open(args.file, encoding="utf-8").read()))
    return 0

def cmd_verify(args):
    orig = open(args.original, encoding="utf-8").read()
    j = load_export(args.export)
    if "results" in j:
        rows = [r for r in j["results"] if page_id(r.get("url", "")) == page_id(args.page_id)]
        if not rows:
            print("导出里找不到该行"); return 2
        v = rows[0].get(args.field)
    else:
        t = j["text"]; v = json.loads(t[t.index("<properties>") + 12: t.index("</properties>")]).get(args.field)
    a, b = norm_hash(demarkdown2(v or "")), norm_hash(orig)
    print(json.dumps({"一致": a == b, "读回还原哈希": a, "原文哈希": b}, ensure_ascii=False))
    return 0 if a == b else 1

# ---------- 自测 ----------
def selftest(args):
    ok = True
    def check(name, cond):
        nonlocal ok
        ok &= bool(cond)
        print(("通过 " if cond else "失败 ") + name)
    cases = ["a*b*c", "C:\\tmp\\x", "字面<br>标签", "[a](b)", "x_y #h ~s~ |t| `c`", "多行\n第二行\n", "【中文】"]
    for s in cases:   # 模拟 Notion：存储=转义解析后的原文，view 渲染时再转义、换行→<br>
        check(f"往返 {s!r}", demarkdown2(escape_md(s).replace("\n", "<br>")) == s)
    check("自动链接还原", demarkdown2("文件 [SKILL.md](http://SKILL.md) 与 x") == "文件 SKILL.md 与 x")
    check("转义的 [a](http://b) 不当链接", demarkdown2(escape_md("[a](http://b)")) == "[a](http://b)")
    check("未转义可疑识别", suspicious_unescaped("中文测试*星号*") and not suspicious_unescaped(escape_md("a*b")))
    check("包裹/无包裹都能解析", load_export_str('<x>\n\n{"a":1}\n\n</x>') == {"a": 1} and load_export_str('{"a":1}') == {"a": 1})
    check("page_id 两种 url", page_id("https://app.notion.com/p/3fbbfd313847814180a0da1b9ee091b5") ==
          page_id("https://app.notion.com/3fbbfd313847814180a0da1b9ee091b5") == "3fbbfd313847814180a0da1b9ee091b5")
    check("筛选识别：advancedFilter", filter_key({"advancedFilter": {"filters": [{"x": 1}]}}) == "advancedFilter")
    check("筛选识别：其他 filter 类键", filter_key({"quickFilters": [{"property": "状态"}]}) == "quickFilters"
          and filter_key({"format": {"filter": {"a": 1}}}) == "format.filter")
    check("筛选识别：分组/空值不算", filter_key({"groupBy": {"hideEmptyGroups": True}, "filter": None, "quickFilters": []}) is None)
    fm1 = "---\nname: 甲\ndescription: 一 二 bot 三\n---\n正文\n"
    fm2 = "---\nname: 甲\ndescription: >-\n  一 二\n  bot 三\nmetadata:\n  k: v\n---\n正文  \n\n"
    check("规范化 v2：描述同值不同写法（单行 / >- 折行 / 多余键）哈希相同", norm_hash(fm1) == norm_hash(fm2))
    check("规范化 v2：改描述哈希变", norm_hash(fm1) != norm_hash(fm1.replace("三", "四")))
    check("规范化 v2：改 name 哈希变", norm_hash(fm1) != norm_hash(fm1.replace("name: 甲", "name: 乙")))
    check("规范化 v2：无 frontmatter 与 v1 相同", normalize("a  \n\nb\n") == "a\n\nb")
    try:
        norm_hash("---\nname: 甲\n---\n正文"); check("规范化 v2：缺 description 报错", False)
    except FrontmatterError:
        check("规范化 v2：缺 description 报错", True)
    fx = args.fixtures
    if fx:
        g = os.path.join(fx, "grouped", "db_fetch.txt")
        if os.path.exists(g):
            check("分组视图（隐藏空组）判为不带筛选", _vf_text(g, "3febfd31-3847-8194-b96d-000c27ae739e") is None)
            check("分组视图（显示空组）判为不带筛选", _vf_text(g, "3febfd31-3847-812a-9afd-000cb39f5d09") is None)
            check("默认（排除已废弃）判为带筛选", (_vf_text(g, "3febfd31-3847-8156-a3c6-000cd7920352") or "").startswith("advancedFilter"))
        e = os.path.join(fx, "boundary", "fetch_E8000.txt")
        o = os.path.join(fx, "boundary", "originals.json")
        if os.path.exists(e) and os.path.exists(o):
            v = fetch_properties(e)["长文"]
            orig = json.load(open(o, encoding="utf-8"))["L8000"]
            check(f"E8000 fetch 还原==原文（{len(v)}→{len(demarkdown2(v))} 字）", demarkdown2(v) == orig)
            r = json.load(open(o, encoding="utf-8"))
            vs = {x["名称"]: x["长文"] for x in load_export(os.path.join(fx, "boundary", "view_p3.txt"))["results"] if x["名称"].startswith("L")}
            for n in sorted(vs, key=lambda k: int(k[1:])):
                check(f"{n} 未转义写入→判为可疑（不误判一致）", suspicious_unescaped(vs[n]) and demarkdown2(vs[n]) != r[n])
        b = os.path.join(fx, "B_view_all.txt"); t = os.path.join(fx, "T_rows.txt")
        if os.path.exists(b) and os.path.exists(t):
            for f in (b, t):
                for r in load_export(f)["results"]:
                    if r.get("设定正文"):
                        check(f"流程治理 {r.get('编号')} 设定正文还原后哈希==登记",
                              norm_hash(demarkdown2(r["设定正文"])) == r["内容哈希"])
    print("自测" + ("全部通过" if ok else "有失败"))
    return 0 if ok else 1

def _vf_text(dbfile, vid):
    t = load_export(dbfile).get("text", "")
    m = re.search(r'<view url="\{\{view://' + re.escape(vid) + r'\}\}">\n(\{.*?\})\n</view>', t, re.S)
    return filter_key(json.loads(m.group(1))) if m else "找不到视图"

def load_export_str(s):
    i, j = s.find("{"), s.rfind("}")
    return json.loads(s[i:j + 1])

def main():
    ap = argparse.ArgumentParser(description="流程治理检查脚本")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--export-dir", required=True)
    r.add_argument("--agents-dir", default="/home/box/agent-data/agents")
    r.add_argument("--workflows-dir", default="/home/box/agent-data/workflows")
    r.add_argument("--prev"); r.add_argument("--out")
    r.add_argument("--skip-view-check", action="store_true", help="只用于自测旧导出：不核对视图是否带筛选")
    e = sub.add_parser("escape"); e.add_argument("file")
    v = sub.add_parser("verify-text"); v.add_argument("--original", required=True); v.add_argument("--export", required=True)
    v.add_argument("--page-id", required=True); v.add_argument("--field", required=True)
    s = sub.add_parser("selftest"); s.add_argument("--fixtures")
    a = ap.parse_args()
    return {"run": run, "escape": cmd_escape, "verify-text": cmd_verify, "selftest": selftest}[a.cmd](a)

if __name__ == "__main__":
    sys.exit(main())
