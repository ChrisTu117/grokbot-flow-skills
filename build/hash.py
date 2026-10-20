"""用法：python3 build/hash.py 路径/SKILL.md [更多路径...]
输出规范化 SHA-256（规范化 v2，与 skill「参谋长治理」第 5 节一致；纯标准库）：
1. 统一换行 LF；
2. 若首行是 ---，到下一个 --- 行为 frontmatter：只取 name 和 description 两个键的值（按 YAML 标量解析：
   普通、单/双引号、折叠 > >-、字面 | |-，多行续行），改写成两行「name: 值」「description: 值」（值里的换行写成 \\n），
   再接一行 ---；其他键（license、metadata 等）不计入。两个键有任何一个解析不了，就报错退出，不出哈希；
3. 去掉每行末尾空白；去掉全文首尾空白行；UTF-8 编码后算 SHA-256。
没有 frontmatter 的文本（bot 设定正文、脚本）与规范化 v1 结果完全相同。
只认值、不认写法：同一描述写成一行，或装机后被改写成 >- 折行，哈希一样。"""
import hashlib, re, sys

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

def norm_hash_text(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()

def norm_hash(path: str) -> str:
    with open(path, encoding="utf-8-sig") as f:
        return norm_hash_text(f.read())

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    bad = 0
    for p in sys.argv[1:]:
        try:
            print(norm_hash(p) + "  " + p)
        except FrontmatterError as e:
            print(f"错误  {p}：{e}", file=sys.stderr); bad = 1
    sys.exit(bad)
