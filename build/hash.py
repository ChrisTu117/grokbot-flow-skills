"""用法：python3 build/hash.py [--project 项目名] 路径 [更多路径...]
输出规范化 SHA-256（与 skill「参谋长治理」第 4 节规范化规则一致）：
去掉 YAML frontmatter（首行为 --- 到下一个 --- 行）；统一换行 LF；去掉每行末尾空白；去掉全文首尾空白行；UTF-8 编码后算 SHA-256。
--project 项目名：先把文中的占位符「〈项目名〉」替换成该项目名再算（用于由副官模板算出某个副官设定应有的哈希）；
只做这一种替换，方向固定为 模板→实例，不反向替换。不加此参数时结果与旧版完全相同。"""
import hashlib, sys

PLACEHOLDER = "〈项目名〉"

def normalize(text: str, project: str | None = None) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1:]
                break
    out = "\n".join(l.rstrip() for l in lines).strip("\n")
    if project is not None:
        out = out.replace(PLACEHOLDER, project)
    return out

def norm_hash(path: str, project: str | None = None) -> str:
    with open(path, encoding="utf-8-sig") as f:
        return hashlib.sha256(normalize(f.read(), project).encode("utf-8")).hexdigest()

if __name__ == "__main__":
    args = sys.argv[1:]
    project = None
    if args[:1] == ["--project"]:
        if len(args) < 2 or not args[1].strip():
            sys.exit("--project 后面要跟项目名")
        project, args = args[1], args[2:]
    if not args:
        sys.exit(__doc__)
    for p in args:
        print(norm_hash(p, project) + "  " + p)
