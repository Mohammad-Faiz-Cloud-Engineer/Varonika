"""Convert LaTeX math into plain readable text.

Qt's markdown renderer does not understand LaTeX, and the speech
formatter does not either, so math like $\tau = r F \\sin(\theta)$ would
otherwise appear raw in the chat and be read out loud as "dollar tau
equals..." This module rewrites the most common LaTeX math into ordinary
text: Greek letters become their Unicode symbols, \frac{a}{b} becomes
(a)/(b), \\sqrt{x} becomes \u221ax, superscripts and subscripts become their
Unicode forms, and any remaining commands keep their letters with the
backslash removed.
"""

import re

_GREEK = {
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
    "epsilon": "\u03b5", "zeta": "\u03b6", "eta": "\u03b7", "theta": "\u03b8",
    "iota": "\u03b9", "kappa": "\u03ba", "lambda": "\u03bb", "mu": "\u03bc",
    "nu": "\u03bd", "xi": "\u03be", "omicron": "\u03bf", "pi": "\u03c0",
    "rho": "\u03c1", "sigma": "\u03c3", "tau": "\u03c4", "upsilon": "\u03c5",
    "phi": "\u03c6", "chi": "\u03c7", "psi": "\u03c8", "omega": "\u03c9",
    "Gamma": "\u0393", "Delta": "\u0394", "Theta": "\u0398", "Lambda": "\u039b",
    "Pi": "\u03a0", "Sigma": "\u03a3", "Phi": "\u03a6", "Psi": "\u03a8",
    "Omega": "\u03a9",
}

_SYMBOL_CMDS = {
    "cdot": "\u00b7", "times": "\u00d7", "circ": "\u00b0", "approx": "\u2248",
    "pm": "\u00b1", "leq": "\u2264", "geq": "\u2265", "neq": "\u2260",
    "infty": "\u221e", "sum": "\u2211", "prod": "\u220f", "int": "\u222b",
    "partial": "\u2202", "ldots": "\u2026", "dots": "\u2026",
    "rightarrow": "\u2192", "leftarrow": "\u2190", "le": "\u2264",
    "ge": "\u2265", "ne": "\u2260", "mid": "|",
}

_SUPER_MAP = {
    "0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074",
    "5": "\u2075", "6": "\u2076", "7": "\u2077", "8": "\u2078", "9": "\u2079",
    "+": "\u207a", "-": "\u207b", "=": "\u207c", "(": "\u207d", ")": "\u207e",
    "n": "\u207f",
}

_SUB_MAP = {
    "0": "\u2080", "1": "\u2081", "2": "\u2082", "3": "\u2083", "4": "\u2084",
    "5": "\u2085", "6": "\u2086", "7": "\u2087", "8": "\u2088", "9": "\u2089",
    "+": "\u208a", "-": "\u208b", "=": "\u208c", "(": "\u208d", ")": "\u208e",
    "a": "\u2090", "e": "\u2091", "o": "\u2092", "x": "\u2093",
    "h": "\u2095", "k": "\u2096", "l": "\u2097", "m": "\u2098",
    "n": "\u2099", "p": "\u209a", "s": "\u209b", "t": "\u209c",
}

_CMD_RE = re.compile(r"\\[a-zA-Z]+")


def _skip_ws(s, i):
    while i < len(s) and s[i] in " \t\n":
        i += 1
    return i


def _take_group(s, i):
    """s[i] must be '{'. Return (content, index after the closing brace)."""
    depth = 0
    j = i
    while j < len(s):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def _super(arg):
    if all(ch in _SUPER_MAP for ch in arg):
        return "".join(_SUPER_MAP[ch] for ch in arg)
    return f"^({arg})"


def _sub(arg):
    if all(ch in _SUB_MAP for ch in arg):
        return "".join(_SUB_MAP[ch] for ch in arg)
    return f"_({arg})"


def _maybe_paren(arg):
    return arg if len(arg) <= 1 else f"({arg})"


def _convert_math(s):
    """Rewrite a single math snippet (no $ delimiters) to readable text."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            match = _CMD_RE.match(s, i)
            if match:
                name = match.group()[1:]
                j = match.end()
                if name in ("frac", "dfrac", "tfrac"):
                    j = _skip_ws(s, j)
                    if j < n and s[j] == "{":
                        num, j = _take_group(s, j)
                        j = _skip_ws(s, j)
                        if j < n and s[j] == "{":
                            den, j = _take_group(s, j)
                            out.append(f"({_convert_math(num)})/({_convert_math(den)})")
                            i = j
                            continue
                        out.append(_convert_math(num))
                        i = j
                        continue
                    out.append(name)
                elif name == "sqrt":
                    j = _skip_ws(s, j)
                    if j < n and s[j] == "{":
                        arg, j = _take_group(s, j)
                        out.append("\u221a" + _maybe_paren(_convert_math(arg)))
                        i = j
                        continue
                    out.append("\u221a")
                elif name in ("left", "right"):
                    j = _skip_ws(s, j)
                    if j < n and s[j] in "()[]{}|.":
                        out.append("" if s[j] == "." else s[j])
                        j += 1
                elif name in _GREEK:
                    out.append(_GREEK[name])
                elif name in _SYMBOL_CMDS:
                    out.append(_SYMBOL_CMDS[name])
                else:
                    out.append(name)
                i = j
                continue
            j = i + 1
            if j < n:
                if s[j] == "\\":
                    out.append("; ")
                else:
                    out.append(" " if s[j] in ",;! " else s[j])
                j += 1
            i = j
        elif c == "$":
            # A stray '$' inside math content (e.g. a degenerate nested
            # span) is never valid LaTeX: drop it rather than render it.
            i += 1
        elif c == "^":
            j = i + 1
            if j < n and s[j] == "{":
                arg, j = _take_group(s, j)
                out.append(_super(_convert_math(arg)))
                i = j
            elif j < n and s[j] == "\\":
                cmd = _CMD_RE.match(s, j)
                if cmd:
                    name = cmd.group()[1:]
                    if name in _GREEK or name in _SYMBOL_CMDS:
                        out.append(_GREEK.get(name) or _SYMBOL_CMDS[name])
                        i = cmd.end()
                        continue
                out.append("^")
                i = j
            elif j < n:
                out.append(_super(s[j]))
                j += 1
                i = j
            else:
                i = j
        elif c == "_":
            j = i + 1
            if j < n and s[j] == "{":
                arg, j = _take_group(s, j)
                out.append(_sub(_convert_math(arg)))
                i = j
            elif j < n and s[j] == "\\":
                cmd = _CMD_RE.match(s, j)
                if cmd:
                    name = cmd.group()[1:]
                    if name in _GREEK or name in _SYMBOL_CMDS:
                        out.append(_GREEK.get(name) or _SYMBOL_CMDS[name])
                        i = cmd.end()
                        continue
                out.append("_")
                i = j
            elif j < n:
                out.append(_sub(s[j]))
                j += 1
                i = j
            else:
                i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _looks_like_math(s):
    """True if a $-delimited span really is math, not currency or prose.

    Real math almost always carries a LaTeX command, a superscript or
    subscript marker, or a Greek letter. Currency and plain numbers carry
    none of these, so their '$' delimiters can be dropped instead of being
    converted as if they were math.
    """
    if "\\" in s or "^" in s or "_" in s:
        return True
    return any("\u03b1" <= ch <= "\u03c9" or "\u0391" <= ch <= "\u03a9" for ch in s)


def _find_next_dollar(text, start):
    """Index of the next inline '$', or -1 if it would cross a fence or a
    '$$' block boundary (a pair must never straddle those)."""
    j = start
    n = len(text)
    while j < n:
        if text[j] == "$":
            if j + 1 < n and text[j + 1] == "$":
                return -1
            if j + 1 < n and text[j + 1].isdigit():
                j += 1
                continue
            return j
        if text[j] == "\n":
            k = j + 1
            while k < n and text[k] in " \t":
                k += 1
            if text.startswith("```", k):
                return -1
        j += 1
    return -1


def latex_to_text(text: str) -> str:
    """Rewrite LaTeX math in a markdown string into readable plain text.

    Fenced code blocks are left untouched, so `$` inside code stays as-is.
    Handles $$...$$ block math, \\(...\\) / \\[...\\] and $...$ inline math.
    A single fence-aware scanner pairs the '$' delimiters by looking at
    the content between them, so currency ("$100"), lone dollars and math
    that spans lines all resolve without ever leaving a raw '$' behind.
    """
    # Pass 1: \(...\) and \[...\] math, fence-aware per line
    lines = text.split("\n")
    out = []
    in_fence = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        line = re.sub(r"\\\[\s*(.*?)\s*\\\]",
                      lambda m: _convert_math(m.group(1)), line, flags=re.DOTALL)
        line = re.sub(r"\\\(\s*(.*?)\s*\\\)",
                      lambda m: _convert_math(m.group(1)), line, flags=re.DOTALL)
        out.append(line)
    text = "\n".join(out)

    # Pass 2: whole-text scan for $$ blocks and $ spans
    out = []
    buf = []
    math_buf = None      # None when not inside a $$ block
    span = None          # None when no inline span is open
    in_fence = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # Fence lines are consumed whole, never scanned
        if i == 0 or text[i - 1] == "\n":
            k = i
            while k < n and text[k] in " \t":
                k += 1
            if text.startswith("```", k):
                if span is not None:
                    buf.append(_convert_math("".join(span))
                               if _looks_like_math("".join(span))
                               else "$" + "".join(span))
                    span = None
                j = text.find("\n", i)
                if j == -1:
                    j = n
                buf.append(text[i:j])
                in_fence = not in_fence
                i = j
                continue
        if in_fence:
            buf.append(ch)
            i += 1
            continue
        if ch == "$" and i + 1 < n and text[i + 1] == "$":
            if span is not None:
                buf.append(_convert_math("".join(span))
                           if _looks_like_math("".join(span))
                           else "$" + "".join(span))
                span = None
            if math_buf is None:
                out.append("".join(buf))
                buf = []
                math_buf = []
            else:
                out.append(_convert_math("".join(math_buf)))
                math_buf = None
            i += 2
            continue
        if math_buf is not None:
            math_buf.append(ch)
            i += 1
            continue
        if ch == "$":
            if i + 1 < n and text[i + 1].isdigit():
                buf.append(ch)
                i += 1
                continue
            close = _find_next_dollar(text, i + 1)
            if close != -1:
                content = text[i + 1:close]
                out.append("".join(buf))
                buf = []
                out.append(_convert_math(content))
                i = close + 1
                continue
            # No closing '$' ahead: treat as literal
            buf.append(ch)
            i += 1
            continue
        if span is not None:
            span.append(ch)
        else:
            buf.append(ch)
        i += 1
    if span is not None:
        buf.append(_convert_math("".join(span))
                   if _looks_like_math("".join(span))
                   else "$" + "".join(span))
    if math_buf is not None:
        out.append(_convert_math("".join(math_buf)))
    out.append("".join(buf))
    return "".join(out)
