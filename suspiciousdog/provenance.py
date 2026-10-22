"""Experiment 1: does the agent write names it has never seen?

When a model writes `client.messages.batch_create(timeout_ms=5)`, every name comes from one of two places: the
context (files read, command output, docs, the user's messages) or its own weights. The transcript shows which:
was the name in front of the agent before it wrote it?

  green   seen in the context first, or defined by the agent itself
  yellow  not seen, but it exists in the repo, the installed dependencies or a man page
  red     not seen and found nowhere: it came from memory

We expected red names to fail more often. On our sessions they don't (see RESULTS.md). Run it on yours.
Claude Code transcripts only, because it needs the full tool output.
"""

import builtins
import json
import keyword
import os
import re
import subprocess
import sys
import sysconfig
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import claude_code

CODE_SUFFIXES = {
    ".py", ".pyi", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts", ".sh", ".bash", ".zsh",
    ".go", ".rs", ".rb", ".php", ".java", ".kt", ".swift", ".c", ".h", ".cpp", ".hpp", ".cs", ".sql",
    ".lua", ".vue", ".svelte", ".astro",
}
WRITING_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}
NOT_EVIDENCE = {"Write", "Edit", "MultiEdit", "NotebookEdit", "TodoWrite", "Agent", "Task"}

WORD = re.compile(r"--?[A-Za-z][\w-]*|[A-Za-z_$][\w$]*")
URL = re.compile(r"https?://\S+")
ATTRIBUTE = re.compile(r"(?<=[\w\)\]'\"`])\.([A-Za-z_$][\w$]{2,})")
CALL = re.compile(r"(?<![\w.$-])([A-Za-z_$][\w$]{2,})\(")
FLAG = re.compile(r"(?<![\w-])(?<!var\()(--[A-Za-z][\w-]{2,})(?![\w-]*\s*:)")
READS_FLAGS = re.compile(r"argparse|sys\.argv|process\.argv|parseArgs|getopt|case\s+[\"']?--|\$\{?1")
COMPOUND = re.compile(r"(?<![\w$.-])([a-z]+[A-Z][\w$]*|[A-Za-z][A-Za-z0-9]*_\w+)\b")
NAME = re.compile(r"[A-Za-z_$][\w$]*")

DEFINITIONS = [
    re.compile(r"\b(?:def|class|function|const|let|var|type|interface|enum|struct|fn|func|trait|namespace)"
               r"\s*\*?\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var|local|readonly|declare)?\s*([A-Za-z_$][\w$.]*)\s*(?::[^=\n]+)?=(?![=>])",
               re.M),
    re.compile(r"\bas\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"^\s*([A-Za-z_$][\w$]*)\s*\(\s*\)\s*\{", re.M),
    re.compile(r"\bcreate\s+(?:or\s+replace\s+)?(?:unique\s+)?(?:materialized\s+)?"
               r"(?:function|table|view|type|index|trigger|policy|procedure|schema|sequence|domain)\s+"
               r"(?:if\s+not\s+exists\s+)?(?:\w+\.)?\"?(\w+)", re.I),
    re.compile(r"\b(?:add|rename)\s+column\s+(?:if\s+not\s+exists\s+)?\"?(\w+)", re.I),
    re.compile(r"\brename\s+(?:column\s+)?\w+\s+to\s+\"?(\w+)", re.I),
    re.compile(r"(?:^|[(,])\s*\"?(\w+)\"?\s+(?:uuid|text|int|integer|bigint|smallint|boolean|bool|jsonb?|"
               r"timestamptz|timestamp|date|time|numeric|decimal|serial|bigserial|real|double|varchar|char|"
               r"bytea|inet|interval|citext)\b", re.I | re.M),
]
DEFINITION_LISTS = [
    re.compile(r"(?:const|let|var)\s*[{\[]([^}\]]*)[}\]]"),
    re.compile(r"\b(?:def|function|fn|func)\s*\*?\s*[\w$]*\s*\(([^)]*)\)"),
    re.compile(r"\(([^()]*)\)\s*(?::\s*[^={]+)?=>"),
    re.compile(r"\bfor\s*\(?\s*(?:const|let|var)?\s*([^;\n]*?)\s+(?:in|of)\b"),
    re.compile(r"\blambda\s+([^:]*):"),
    re.compile(r"\b(?:interface|type)\s+\w+[^{]*\{([^}]*)\}"),
    re.compile(r"\bclass\s+\w+[^:{]*[:{]((?:\n[ \t]+\w+\s*:[^\n]*)+)"),
]
ERROR_SIGNS = re.compile(
    r"has no attribute|is not a function|is not defined|not defined|unknown option|unrecognized|"
    r"unexpected (?:keyword )?argument|unknown (?:flag|argument|command|column|field|property)|"
    r"does not exist|cannot find|no module named|not found|undefined|invalid (?:option|argument)|"
    r"no such (?:option|column|table|function)|could not resolve|is not exported|unknown",
    re.I,
)


def _well_known():
    known = set(keyword.kwlist) | set(getattr(keyword, "softkwlist", []))
    known |= set(dir(builtins))
    for kind in (str, bytes, list, dict, set, frozenset, tuple, int, float, complex, object, BaseException, type):
        known |= set(dir(kind))
    known |= set(getattr(sys, "stdlib_module_names", ()))
    known |= set("""
        abstract arguments async await boolean break byte case catch char class const continue debugger default
        delete do double else enum eval export extends false final finally float for function goto if implements
        import in instanceof int interface let long native new null package private protected public return short
        static super switch synchronized this throw throws transient true try typeof var void volatile while with
        yield undefined NaN Infinity globalThis window document console log warn error info debug table time
        timeEnd Object Array String Number Boolean Symbol BigInt Math Date RegExp Error TypeError RangeError
        SyntaxError JSON Promise Map Set WeakMap WeakSet Proxy Reflect Intl parseInt parseFloat isNaN isFinite
        encodeURIComponent decodeURIComponent encodeURI decodeURI setTimeout clearTimeout setInterval
        clearInterval queueMicrotask structuredClone fetch Response Request Headers URL URLSearchParams FormData
        Blob File FileReader TextEncoder TextDecoder AbortController AbortSignal Event CustomEvent EventTarget
        crypto randomUUID getRandomValues localStorage sessionStorage navigator location history require module
        exports process env argv cwd exit Buffer __dirname __filename length push pop shift unshift slice splice
        concat join reverse sort indexOf lastIndexOf includes find findIndex findLast filter map reduce
        reduceRight forEach some every flat flatMap fill keys values entries from isArray assign freeze create
        defineProperty getPrototypeOf hasOwnProperty toString valueOf toFixed toLowerCase toUpperCase trim
        trimStart trimEnd split replace replaceAll match matchAll search startsWith endsWith padStart padEnd
        repeat charAt charCodeAt codePointAt substring substr localeCompare normalize then catch finally resolve
        reject all allSettled race any stringify parse now getTime toISOString getFullYear getMonth getDate
        getDay getHours getMinutes getSeconds toLocaleDateString toLocaleString toLocaleTimeString floor ceil
        round abs max min pow sqrt random sign trunc log10 PI get set has add clear size delete next done value
        prototype constructor call apply bind name message stack cause test exec lastIndex source flags
        addEventListener removeEventListener dispatchEvent preventDefault stopPropagation target currentTarget
        querySelector querySelectorAll getElementById getElementsByClassName createElement appendChild
        removeChild insertBefore setAttribute getAttribute removeAttribute classList contains toggle style
        innerHTML textContent innerText dataset parentNode children firstChild closest matches focus blur click
        json text arrayBuffer status statusText ok body method headers signal append string number object
        bigint symbol never unknown readonly keyof infer satisfies Partial Required Readonly Record Pick Omit
        Exclude Extract NonNullable ReturnType Parameters Awaited declare useState useEffect useMemo useCallback
        useRef useContext useReducer echo printf cd ls cat grep sed awk head tail sort uniq wc cut tr xargs find
        mkdir rmdir rm cp mv ln chmod chown touch test source export unset local read shift trap wait kill sleep
        true false then fi elif esac done do help version
    """.split())
    known |= {"--help", "--version"}
    known |= {"py", "js", "ts", "tsx", "jsx", "json", "md", "txt", "html", "css", "sql", "yaml", "yml", "toml", "png",
              "jpg", "jpeg", "svg", "pdf", "csv", "log", "env", "lock", "mjs", "cjs", "com", "org", "net", "dev",
              "app", "www", "docx", "xlsx", "gif", "webp", "mp4", "zip", "gz", "tar", "sh", "local", "example"}
    return known


KNOWN = _well_known()


@dataclass
class Write:
    index: int
    tool: str
    path: str
    text: str
    id: str
    ok: bool = True


@dataclass
class Session:
    path: Path
    cwd: str = ""
    seen: dict = field(default_factory=dict)       # word -> index of the first event that showed it
    writes: list = field(default_factory=list)
    errors: list = field(default_factory=list)     # (index, text) of failed tool results


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def _result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _written(tool, args):
    """What the agent wrote with the tool, and the evidence the tool itself carries (the old text of an edit)."""
    if tool == "Write":
        return args.get("file_path", ""), args.get("content", ""), ""
    if tool == "Edit":
        return args.get("file_path", ""), args.get("new_string", ""), args.get("old_string", "")
    if tool == "MultiEdit":
        edits = args.get("edits") or []
        return (args.get("file_path", ""), "\n".join(e.get("new_string", "") for e in edits),
                "\n".join(e.get("old_string", "") for e in edits))
    if tool == "NotebookEdit":
        return args.get("notebook_path", ""), args.get("new_source", ""), ""
    if tool == "Bash":
        return "Bash", args.get("command", ""), ""
    return "", "", ""


def read(path):
    s = Session(Path(path))
    uses = {}
    written_files = set()     # names of files the agent wrote, to ignore echoes of its own code
    index = 0

    def see(text):
        for w in WORD.findall(URL.sub(" ", text)):
            s.seen.setdefault(w, index)

    with open(path, errors="replace") as f:
        lines = f.readlines()
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        index += 1
        s.cwd = s.cwd or d.get("cwd", "")
        kind = d.get("type")
        message = d.get("message") if isinstance(d.get("message"), dict) else {}
        content = message.get("content")
        if kind == "attachment":
            see("\n".join(_strings(d.get("attachment"))))
        elif kind == "user":
            if isinstance(content, str):
                see(content)
                continue
            for b in content or []:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    see(b.get("text", ""))
                elif b.get("type") == "tool_result":
                    tool, args = uses.get(b.get("tool_use_id"), ("", {}))
                    text = _result_text(b.get("content"))
                    failed = bool(b.get("is_error"))
                    for w in s.writes:
                        if w.id == b.get("tool_use_id"):
                            w.ok = not failed
                    if failed:
                        s.errors.append((index, text))
                        continue
                    if tool in NOT_EVIDENCE:
                        continue
                    if tool == "Read" and Path(args.get("file_path", "")).name in written_files:
                        continue
                    if tool == "Bash" and any(n in args.get("command", "") for n in written_files):
                        continue
                    see("\n".join(r for r in text.splitlines() if not any(n in r for n in written_files)))
        elif kind == "assistant":
            for b in content or []:
                if not isinstance(b, dict) or b.get("type") != "tool_use":
                    continue
                tool, args = b.get("name", ""), b.get("input") or {}
                uses[b.get("id")] = (tool, args)
                if tool not in WRITING_TOOLS:
                    continue
                file, new, old = _written(tool, args)
                see(old)
                if tool != "Bash":
                    written_files.add(Path(file).name)
                    if Path(file).suffix.lower() not in CODE_SUFFIXES:
                        continue
                s.writes.append(Write(index, tool, file, new, b.get("id", "")))
    return s


def candidates(text, bash=False):
    """The names a piece of code claims exist: attributes, calls, flags, compound identifiers."""
    text = URL.sub(" ", text)
    found = set(ATTRIBUTE.findall(text)) | set(CALL.findall(text)) | set(COMPOUND.findall(text))
    found |= set(FLAG.findall(text))
    if bash:
        found = {t for t in found if t.startswith("--") or "_" in t or not t.islower()}
    return {t for t in found if t not in KNOWN and len(t.lstrip("-")) >= 3 and not t.lstrip("-").isdigit()}


def defined(texts):
    """Names the agent coined: functions, classes, variables, parameters, fields of its own types and tables."""
    names = set()
    for text in texts:
        for r in DEFINITIONS:
            for m in r.findall(text):
                names.update(m.split("."))
        for r in DEFINITION_LISTS:
            for group in r.findall(text):
                for part in re.split(r"[,;\n]", group):
                    m = NAME.search(part.strip().lstrip("*.").strip())
                    if m:
                        names.add(m.group())
    return names


def _dependency_dirs(cwd):
    dirs = []
    p = Path(cwd) if cwd else None
    for _ in range(4):
        if not p or not p.exists():
            break
        for name in ("node_modules", ".venv", "venv"):
            if (p / name).is_dir():
                dirs.append(p / name)
        p = p.parent
    for key in ("stdlib", "purelib"):
        path = sysconfig.get_paths().get(key)
        if path and Path(path).is_dir():
            dirs.append(Path(path))
    return dirs


def in_the_world(names, cwd, written):
    """Which names really exist in the repo (minus the agent's own files) or in the dependencies."""
    names = sorted(n for n in names if not n.startswith("--"))
    if not names:
        return set()
    found = set()
    patterns = "\n".join(names)
    skip = {str(Path(p).resolve()) for p in written if p and p != "Bash"}
    searches = [["--max-filesize", "2M", cwd]] if cwd and Path(cwd).is_dir() else []
    searches += [["--no-ignore", "--hidden", "--max-filesize", "2M", str(d)] for d in _dependency_dirs(cwd)]
    for extra in searches:
        try:
            out = subprocess.run(
                ["rg", "--no-messages", "-o", "-w", "-F", "--with-filename", "--no-line-number", "-f", "-", *extra],
                input=patterns, capture_output=True, text=True, timeout=30,
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in out.splitlines():
            file, _, name = line.rpartition(":")
            if name and str(Path(file).resolve()) not in skip:
                found.add(name)
    return found


def _commands(w):
    """Commands in a shell line, with git-style subpages: `git log` is also `git-log`."""
    if w.tool != "Bash":
        return []
    out = []
    pattern = r"(?:^|[|;&(]\s*|\$\(\s*|\b(?:sudo|timeout \d+|npx|xargs)\s+)([a-z][\w.-]*)(?:\s+([a-z][\w-]*))?"
    for c, sub in re.findall(pattern, w.text, re.M):
        out.append(c)
        if sub:
            out.append(f"{c}-{sub}")
    return list(dict.fromkeys(out))


_MAN = {}


def _man(command):
    """The man page text. Reading documentation runs nothing."""
    if command not in _MAN:
        try:
            _MAN[command] = subprocess.run(["man", "-P", "cat", command], capture_output=True, text=True,
                                           timeout=5, env={**os.environ, "MANWIDTH": "200"}).stdout
        except (OSError, subprocess.TimeoutExpired):
            _MAN[command] = ""
    return _MAN[command]


def _in_man(name, commands):
    pattern = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
    return any(pattern.search(_man(c).replace("‐", "-")) for c in commands)


@dataclass
class Name:
    name: str
    colour: str
    write: Write
    context: str
    error: str = ""
    verified_later: bool = False


def _seen_before(s, n, index):
    return s.seen.get(n, index) < index or (not n.startswith("--") and s.seen.get(n.lstrip("-"), index) < index)


def _context(text, name):
    for line in text.splitlines():
        if name in line:
            return line.strip()[:140]
    return ""


def _later_error(s, name):
    """The first failed tool result after the write that names this name next to an error sign."""
    pattern = re.compile(r"(?<![\w$-])" + re.escape(name.name) + r"(?![\w$-])")
    for index, text in s.errors:
        if index <= name.write.index:
            continue
        for m in pattern.finditer(text):
            around = text[max(0, m.start() - 80): m.end() + 80]
            if ERROR_SIGNS.search(around):
                return around.replace("\n", " ").strip()
    return ""


def analyse(s, world=True):
    """Colours every name the agent wrote, as it stood at the moment it was written."""
    coined = defined(w.text for w in s.writes if w.tool != "Bash" or "<<" in w.text)
    pending = defaultdict(list)
    results = []
    for w in (w for w in s.writes if w.ok):
        own_flags = w.tool != "Bash" and READS_FLAGS.search(w.text)
        for n in candidates(w.text, bash=w.tool == "Bash"):
            bare = n.lstrip("-")
            if _seen_before(s, n, w.index) or bare in coined or n in coined or (n.startswith("--") and own_flags):
                colour = "green"
            else:
                colour = "?"
            name = Name(n, colour, w, _context(w.text, n))
            name.verified_later = colour == "?" and (n in s.seen or bare in s.seen and not n.startswith("--"))
            results.append(name)
            if colour == "?":
                pending[n].append(name)
    existing = in_the_world({n.lstrip("-") for n in pending}, s.cwd, [w.path for w in s.writes]) if world else set()
    for n, names in pending.items():
        colour = "yellow" if n.lstrip("-") in existing else "red"
        if world and colour == "red" and any(_in_man(n, _commands(x.write)) for x in names[:3]):
            colour = "yellow"
        for x in names:
            x.colour = colour
    for x in results:
        x.error = _later_error(s, x)
    return results


COLOURS = {"green": "32", "yellow": "33", "red": "31"}


def _paint(text, colour):
    return text if not sys.stdout.isatty() else f"\033[{COLOURS[colour]}m{text}\033[0m"


def report(path, world=True):
    s = read(path)
    unique = {}
    for n in analyse(s, world):
        unique.setdefault((n.name, n.colour), n)
    count = Counter(c for _, c in unique)
    print(f"\n  {Path(path).name} · {s.cwd}")
    print(f"  {sum(count.values())} names written: {count['green']} on evidence, {count['yellow']} real but unread, "
          f"{count['red']} from memory\n")
    for colour, title in (("red", "From memory: never seen, found nowhere"), ("yellow", "Real, but the agent never read them")):
        group = [n for (_, c), n in unique.items() if c == colour]
        if not group:
            continue
        print("  " + _paint(title, colour))
        by_file = defaultdict(list)
        for n in group:
            by_file[n.write.path].append(n)
        for file, names in by_file.items():
            print(f"    {file}")
            for n in sorted(names, key=lambda n: n.name):
                failed = f"  → failed: {n.error[:90]}" if n.error else ""
                print(f"      {_paint(n.name, colour)}  {n.context[:90]}{failed}")
        print()


def history(world=False):
    totals, failed = Counter(), Counter()
    files = claude_code.default_paths()
    for path in files:
        try:
            names = analyse(read(path), world)
        except Exception as e:  # one unreadable session must not stop the rest
            print(f"  skipping {path.name}: {e}", file=sys.stderr)
            continue
        seen = set()
        for n in names:
            key = (n.name, n.write.index)
            if key in seen:
                continue
            seen.add(key)
            totals[n.colour] += 1
            failed[n.colour] += bool(n.error)
    print(f"\n  {len(files)} sessions, {sum(totals.values())} names written\n")
    print(f"    {'':8} {'names':>8} {'then failed':>12} {'rate':>8}")
    for colour in ("green", "yellow", "red"):
        if totals[colour]:
            print(f"    {colour:8} {totals[colour]:>8} {failed[colour]:>12} {failed[colour] / totals[colour]:>8.2%}")
    print("\n  If red doesn't fail more than green, your model's memory is fine. Ours is.\n")


def main(args):
    if args.history:
        return history(args.world)
    path = args.session
    if not path:
        files = sorted(claude_code.default_paths(), key=lambda p: p.stat().st_mtime)
        if not files:
            sys.exit("No Claude Code sessions found.")
        path = files[-1]
    report(path, world=True)
