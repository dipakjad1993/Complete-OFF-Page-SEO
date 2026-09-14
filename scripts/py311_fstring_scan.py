"""Tokenizer-level Python 3.11 compat scan for f-strings.

Must run on ANY interpreter (dev may be 3.12+/3.13, CI is 3.11), so it uses
two paths:
 - 3.12+ tokenizers emit FSTRING_START/MIDDLE/END: any STRING literal found
   inside an f-string whose quote matches the single-quoted outer f-string
   is a 3.11 SyntaxError (PEP 701 nesting).
 - 3.11 tokenizers emit the whole f-string as one STRING token: the body is
   parsed manually for the same violations (and the 3.11 tokenizer itself
   raises TokenError on such files, which is also reported).

Also flags single-quoted f-strings spanning multiple physical lines.
Exit 1 on any finding.
"""

import io
import pathlib
import re
import sys
import tokenize

ROOTS = [pathlib.Path("backend"), pathlib.Path("config"),
         pathlib.Path("scripts"), pathlib.Path("tests"),
         pathlib.Path("main.py"), pathlib.Path("mcp_server.py"),
         pathlib.Path("setup.py")]
SKIP_DIRS = {"__pycache__"}
STR_PREFIX = re.compile(r"(?i)^([a-z]*)('''|\"\"\"|'|\")")
HAS_FTOK = hasattr(tokenize, "FSTRING_START")


def files():
    out = []
    for r in ROOTS:
        if r.is_file():
            out.append(r)
        elif r.is_dir():
            out.extend(sorted(r.rglob("*.py")))
    return [f for f in out if not any(d in f.parts for d in SKIP_DIRS)]


def split_prefix(tstr):
    m = STR_PREFIX.match(tstr)
    if not m:
        return "", ""
    return m.group(1).lower(), m.group(2)


def skip_string(body, i):
    n = len(body)
    ch = body[i]
    q = ch * 3 if body.startswith(ch * 3, i) else ch
    j = i + len(q)
    while j < n:
        if body[j] == "\\":
            j += 2
            continue
        if body.startswith(q, j):
            return j + len(q)
        j += 1
    return n


def scan_body(body, outer, outer_triple, path, row):
    """Manual single-level scan of one f-string body (3.11 single-token path)."""
    problems = []
    depth = 0
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if depth == 0:
            if ch == "{":
                if body.startswith("{{", i):
                    i += 2
                    continue
                depth += 1
            i += 1
            continue
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            depth -= 1
            i += 1
            continue
        if ch in ("'", '"'):
            # nested f-string? compare its quote against the outer (triple
            # outers legally nest single-line different-quote f-strings)
            qlen = 3 if body.startswith(ch * 3, i) else 1
            k = i - 1
            while k >= 0 and body[k].isalpha():
                k -= 1
            pre = body[k + 1:i].lower()
            if pre.endswith("f") and all(c in "rubf" for c in pre):
                if ch == outer and qlen == 1 and not outer_triple:
                    problems.append(
                        f"{path}:{row}: nested same-quote f-string "
                        f"(PEP 701 only, SyntaxError on 3.11)")
                i = skip_string(body, i)
                continue
            if ch == outer and qlen == 1 and not outer_triple:
                problems.append(
                    f"{path}:{row}: nested {ch!r}-quoted string inside "
                    f"{outer!r}-quoted f-string (PEP 701 only, SyntaxError on 3.11)")
            i = skip_string(body, i)
            continue
        i += 1
    return problems


def check_new_tokenizer(toks, path):
    """3.12+ path: FSTRING_START/END stack + inner STRING quote comparison."""
    problems = []
    fstack = []  # [outer_quote, outer_triple, start_row]
    for tok in toks:
        ttype = tok.type
        if ttype == tokenize.FSTRING_START:
            prefix, quote = split_prefix(tok.string)
            triple = len(quote) == 3
            if not triple and tok.end[0] != tok.start[0]:
                # multiline single-quoted f-string (END row differs)
                pass  # judged at FSTRING_END below (rows known there)
            fstack.append([quote[0], triple, tok.start[0], tok.string])
        elif ttype == tokenize.FSTRING_END:
            if fstack:
                q, triple, srow, _ = fstack.pop()
                if not triple and tok.end[0] != srow:
                    problems.append(
                        f"{path}:{srow}: multiline single-quoted f-string "
                        f"(PEP 701 only, SyntaxError on 3.11)")
        elif ttype == tokenize.STRING and fstack:
            prefix, quote = split_prefix(tok.string)
            if not quote:
                continue
            outer, outer_triple = fstack[-1][0], fstack[-1][1]
            inner_triple = len(quote) == 3
            if quote[0] == outer and not outer_triple and not inner_triple:
                problems.append(
                    f"{path}:{tok.start[0]}: nested {quote[0]!r}-quoted string inside "
                    f"{outer!r}-quoted f-string (PEP 701 only, SyntaxError on 3.11): "
                    f"{tok.string[:90]}")
    return problems


def check_old_tokenizer(toks, path):
    """3.11 path: whole f-strings arrive as single STRING tokens."""
    problems = []
    for tok in toks:
        if tok.type == tokenize.STRING:
            prefix, quote = split_prefix(tok.string)
            if "f" not in prefix or not quote:
                continue
            triple = len(quote) == 3
            if not triple and tok.end[0] != tok.start[0]:
                problems.append(
                    f"{path}:{tok.start[0]}: multiline single-quoted f-string "
                    f"(PEP 701 only, SyntaxError on 3.11)")
                continue
            body = tok.string[len(prefix) + len(quote):-len(quote)]
            problems.extend(scan_body(body, quote[0], triple, path, tok.start[0]))
    return problems


def check_file(path):
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(
            path.read_text(encoding="utf-8", errors="replace")).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError) as e:
        return [f"{path}: tokenizer rejects file: {e}"]
    if HAS_FTOK:
        return check_new_tokenizer(toks, path)
    return check_old_tokenizer(toks, path)


def main():
    all_problems = []
    n = 0
    for f in files():
        n += 1
        all_problems.extend(check_file(f))
    if all_problems:
        print("PY311 F-STRING VIOLATIONS:")
        for p in all_problems:
            print(" ", p)
        sys.exit(1)
    print(f"py311 f-string scan OK: {n} files clean")


if __name__ == "__main__":
    main()
