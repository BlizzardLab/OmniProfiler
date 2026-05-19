import re
from typing import List

# Common function/storage/calling convention specifiers (not the type itself)
FUNC_SPECIFIERS = {
    "extern", "static", "inline", "virtual", "explicit", "friend",
    "constexpr", "consteval", "constinit", "typename", "class",
    "register", "thread_local", "volatile", "mutable",
    "__forceinline", "__inline", "__inline__", "__stdcall",
    "__cdecl", "__thiscall", "__fastcall", "__vectorcall",
    "noexcept"
}

# Top-level type qualifiers to be removed
TYPE_QUALIFIERS = {
    "const", "volatile", "mutable", "restrict", "__restrict",
    "__restrict__", "_Nonnull", "_Nullable", "_Null_unspecified"
}

# C/C++ built-in composite type normalization priority
BUILTIN_TYPE_PATTERNS = [
    ["unsigned", "long", "long", "int"],
    ["signed", "long", "long", "int"],
    ["unsigned", "long", "long"],
    ["signed", "long", "long"],
    ["long", "long", "int"],
    ["long", "long"],

    ["unsigned", "long", "int"],
    ["signed", "long", "int"],
    ["unsigned", "long"],
    ["signed", "long"],
    ["long", "int"],
    ["long"],

    ["unsigned", "short", "int"],
    ["signed", "short", "int"],
    ["unsigned", "short"],
    ["signed", "short"],
    ["short", "int"],
    ["short"],

    ["unsigned", "int"],
    ["signed", "int"],
    ["unsigned"],
    ["signed"],
    ["int"],

    ["unsigned", "char"],
    ["signed", "char"],
    ["char"],

    ["wchar_t"],
    ["char8_t"],
    ["char16_t"],
    ["char32_t"],

    ["bool"],
    ["float"],
    ["double"],
    ["long", "double"],
    ["void"],

    ["size_t"],
    ["ssize_t"],
    ["ptrdiff_t"],
    ["std", "::", "size_t"],
]

IDENT_RE = re.compile(r'[A-Za-z_]\w*')
ALL_CAPS_MACRO_RE = re.compile(r'^[A-Z_][A-Z0-9_]*$')


def strip_attributes_and_declspec(s: str) -> str:
    """Remove [[...]], __attribute__((...)), __declspec(...) and similar prefix/infix attributes."""
    # Remove [[...]] (supports common scenarios before simple nesting)
    s = re.sub(r'\[\[.*?\]\]', ' ', s)

    # Remove GNU/Clang attribute
    s = re.sub(r'__attribute__\s*\(\(.*?\)\)', ' ', s)

    # Remove MSVC declspec
    s = re.sub(r'__declspec\s*\(.*?\)', ' ', s)

    # Remove C++11 alignas(...)
    s = re.sub(r'alignas\s*\(.*?\)', ' ', s)

    return s


def collapse_spaces(s: str) -> str:
    s = re.sub(r'\s+', ' ', s).strip()
    # Clean up spaces around :: (namespace/class qualifiers)
    s = re.sub(r'\s*::\s*', '::', s)
    # Clean up spaces around template angle brackets (conservative)
    s = re.sub(r'\s*<\s*', '<', s)
    s = re.sub(r'\s*>\s*', '>', s)
    s = re.sub(r'\s*,\s*', ', ', s)
    return s


def tokenize_cpp_type(s: str) -> List[str]:
    """
    Coarse-grained tokenizer:
    - Identifiers
    - ::
    - < > , * & && [ ]
    - Other single-character symbols
    """
    tokens = []
    i = 0
    n = len(s)

    while i < n:
        c = s[i]

        if c.isspace():
            i += 1
            continue

        if s.startswith("::", i):
            tokens.append("::")
            i += 2
            continue

        if s.startswith("&&", i):
            tokens.append("&&")
            i += 2
            continue

        if c in "<>,*&()[]":
            tokens.append(c)
            i += 1
            continue

        m = IDENT_RE.match(s, i)
        if m:
            tokens.append(m.group(0))
            i = m.end()
            continue

        # Other characters are kept as-is (try not to lose information)
        tokens.append(c)
        i += 1

    return tokens


def remove_leading_macros_and_specifiers(tokens: List[str]) -> List[str]:
    """
    Remove from left to right:
    - Common function specifiers
    - All-uppercase macros that look like "export macros/specifier macros"
    - Top-level const/volatile, etc. (if they appear at the beginning)
    """
    i = 0
    while i < len(tokens):
        t = tokens[i]

        # Common identifiers
        if re.match(r'^[A-Za-z_]\w*$', t):
            if t in FUNC_SPECIFIERS or t in TYPE_QUALIFIERS:
                i += 1
                continue

            # Heuristic: all-uppercase macros are usually export/calling convention/annotation macros
            # But something like UINT32 could also be a type, so only strip them in the "prefix phase"
            if ALL_CAPS_MACRO_RE.match(t):
                i += 1
                continue

        break

    return tokens[i:]


def strip_trailing_name(tokens: List[str]) -> List[str]:
    """
    If a parameter type string contains a variable name (e.g., 'const std::string& name'),
    attempt to strip the trailing name.
    Rules:
    - If the last token is an identifier
    - And the previous token is not :: (to exclude the last part of 'ns::Type')
    - And we are not inside template parameters
    """
    if not tokens:
        return tokens

    # Only strip if the last token is a valid identifier and not part of a qualified name or template
    if not re.match(r'^[A-Za-z_]\w*$', tokens[-1]):
        return tokens

    # Heuristic: it looks more like a variable name than the last part of a type
    # The previous token is not ::, not <, and the overall length is sufficient
    if len(tokens) >= 2 and tokens[-2] not in {"::", "<"}:
        # For example: const Foo& x  -> remove x
        # But: std::vector<int> -> the last token is not an identifier? It's >, so don't remove
        #      Foo -> only one token, don't remove
        if len(tokens) > 1:
            return tokens[:-1]

    return tokens


def strip_top_level_cv_and_ptr_ref(tokens: List[str]) -> List[str]:
    """
    Remove top-level const/volatile and top-level * / & / &&.
    Only process tokens at template depth 0.
    """
    # First, remove top-level const/volatile/mutable
    result = []
    depth_angle = 0
    for t in tokens:
        if t == "<":
            depth_angle += 1
            result.append(t)
        elif t == ">":
            depth_angle = max(0, depth_angle - 1)
            result.append(t)
        elif depth_angle == 0 and t in TYPE_QUALIFIERS:
            continue
        else:
            result.append(t)

    # Then, remove top-level * / & / &&
    result2 = []
    depth_angle = 0
    for t in result:
        if t == "<":
            depth_angle += 1
            result2.append(t)
        elif t == ">":
            depth_angle = max(0, depth_angle - 1)
            result2.append(t)
        elif depth_angle == 0 and t in {"*", "&", "&&"}:
            continue
        else:
            result2.append(t)

    return result2


def remove_elaborated_keywords(tokens: List[str]) -> List[str]:
    """
    Remove elaborated keywords like struct/class/enum/union if they appear as type prefixes.
    """
    if tokens and tokens[0] in {"struct", "class", "enum", "union"}:
        return tokens[1:]
    return tokens


def match_builtin_type(tokens: List[str]) -> str | None:
    """
    Identify built-in composite types, such as unsigned long long / long double.
    Only match in simple top-level scenarios.
    """
    # Only take the top-level consecutive "identifier/::" segments for matching
    simple = []
    depth = 0
    for t in tokens:
        if t == "<":
            break
        if t == ">":
            break
        if t in {"*", "&", "&&", ",", "(", ")", "[", "]"}:
            break
        simple.append(t)

    for pat in BUILTIN_TYPE_PATTERNS:
        if simple[:len(pat)] == pat:
            return "".join(
                (" " + x if x not in {"::"} and idx > 0 and pat[idx - 1] != "::" else x)
                for idx, x in enumerate(pat)
            ).strip()

    return None


def tokens_to_string(tokens: List[str]) -> str:
    """
    Reconstruct a more natural type string from tokens.
    """
    if not tokens:
        return ""

    out = []
    prev = None
    for t in tokens:
        if not out:
            out.append(t)
        elif t in {">", ",", "]", ")"}:
            out.append(t)
        elif prev in {"<", "::", "(", "["}:
            out.append(t)
        elif t in {"::", "<", "(", "["}:
            out.append(t)
        else:
            out.append(" " + t)
        prev = t

    s = "".join(out)
    s = s.replace(" ,", ",")
    s = s.replace(" <", "<")
    s = s.replace(" >", ">")
    s = s.replace(" ::", "::")
    return s.strip()


def extract_base_type(type_str: str) -> str:
    s = type_str.strip()
    if not s:
        return ""

    # 1) Remove attributes
    s = strip_attributes_and_declspec(s)
    s = collapse_spaces(s)

    # 2) Tokenize
    tokens = tokenize_cpp_type(s)

    # 3) Remove leading macros and specifiers
    tokens = remove_leading_macros_and_specifiers(tokens)

    # 4) Remove possible parameter names
    tokens = strip_trailing_name(tokens)

    # 5) Remove elaborated keywords
    tokens = remove_elaborated_keywords(tokens)

    # 6) Remove top-level cv / pointer / reference qualifiers
    tokens = strip_top_level_cv_and_ptr_ref(tokens)

    # 7) Remove elaborated keywords again (e.g., 'const struct Foo*')
    tokens = remove_elaborated_keywords(tokens)

    # 8) Normalize built-in types first
    builtin = match_builtin_type(tokens)
    if builtin:
        return builtin

    # 9) If it's an array declaration, like int[10] / Foo[]
    # Here we keep the main type and remove the top-level array part
    cleaned = []
    depth_angle = 0
    depth_bracket = 0
    for t in tokens:
        if t == "<":
            depth_angle += 1
            cleaned.append(t)
        elif t == ">":
            depth_angle = max(0, depth_angle - 1)
            cleaned.append(t)
        elif t == "[" and depth_angle == 0:
            depth_bracket += 1
            # Top-level array dimensions are not counted in the base type
        elif t == "]" and depth_angle == 0 and depth_bracket > 0:
            depth_bracket -= 1
        elif depth_bracket == 0:
            cleaned.append(t)

    return tokens_to_string(cleaned)


if __name__ == "__main__":
    tests = [
        "UNIV_INLINE buf_page_t *",
    ]

    for t in tests:
        print(f"{t!r}  ->  {extract_base_type(t)!r}")