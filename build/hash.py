"""用法：python3 build/hash.py 路径/SKILL.md [更多路径...]
输出规范化 SHA-256（与 skill「参谋长治理」第 5 节规范化规则一致）：
去掉 YAML frontmatter（首行为 --- 到下一个 --- 行）；统一换行 LF；去掉每行末尾空白；去掉全文首尾空白行；UTF-8 编码后算 SHA-256。"""
import hashlib, sys

def normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1:]
                break
    return "\n".join(l.rstrip() for l in lines).strip("\n")

def norm_hash(path: str) -> str:
    with open(path, encoding="utf-8-sig") as f:
        return hashlib.sha256(normalize(f.read()).encode("utf-8")).hexdigest()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        print(norm_hash(p) + "  " + p)
