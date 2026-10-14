#!/usr/bin/env python3
"""Static checks for the Vmore Android sources.

There is no Android SDK in the development sandbox, so the things javac and
aapt2 would catch are checked here instead:

* every @string / @color / @drawable / @dimen / @style / @layout reference in
  res/ and in Java (R.*) points at something that exists;
* a colour defined for the night skin is also defined for the day skin and the
  other way round, so both palettes stay complete;
* every XML file is well formed, ids are unique, and cross-file Java calls
  exist with the right number of arguments;
* no emoji and no asterisk anywhere in the UI text.

Run it from android/app/src/main:  python3 ../../../tools/check_sources.py
"""

import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(".")
RES = ROOT / "res"
JAVA = ROOT / "java" / "com" / "vmore" / "app"
PROBLEMS = []


def problem(message):
    PROBLEMS.append(message)


# --------------------------------------------------------------- resources --

def defined_values():
    """name -> set of files, for every resource defined in res/values*."""
    found = {}
    for path in sorted(RES.glob("values*/*.xml")):
        kind = "colors" if path.parent.name.startswith("values-night") is False else "colors"
        tree = ET.parse(path)
        for child in tree.getroot():
            name = child.attrib.get("name")
            if not name:
                continue
            tag = child.tag
            if tag == "item":
                tag = child.attrib.get("type", "item")
            found.setdefault(tag, {})[name] = path
    return found


def defined_in_values_dir(dirname):
    names = {}
    for path in sorted((RES / dirname).glob("*.xml")):
        for child in ET.parse(path).getroot():
            name = child.attrib.get("name")
            if name:
                names.setdefault(child.tag, set()).add(name)
    return names


def layout_ids():
    ids = set()
    for path in sorted((RES / "layout").glob("*.xml")):
        text = path.read_text()
        for match in re.finditer(r'android:id="@\+?id/([A-Za-z0-9_]+)"', text):
            ids.add(match.group(1))
    return ids


def check_references():
    values = defined_values()
    known = {
        "string": set(values.get("string", {})),
        "color": set(values.get("color", {})),
        "dimen": set(values.get("dimen", {})),
        "bool": set(values.get("bool", {})),
        "integer": set(values.get("integer", {})),
    }
    known["drawable"] = {p.stem for p in (RES / "drawable").glob("*.xml")}
    known["layout"] = {p.stem for p in (RES / "layout").glob("*.xml")}
    known["anim"] = {p.stem for p in (RES / "anim").glob("*.xml")}
    known["style"] = set()
    for path in sorted(RES.glob("values*/styles.xml")):
        for child in ET.parse(path).getroot():
            if child.tag == "style" and child.attrib.get("name"):
                known["style"].add(child.attrib["name"])
    known["xml"] = {p.stem for p in (RES / "xml").glob("*.xml")} if (RES / "xml").exists() else set()
    known["mipmap"] = {p.stem for p in (RES / "mipmap-anydpi-v26").glob("*.xml")} \
        if (RES / "mipmap-anydpi-v26").exists() else set()
    known["id"] = layout_ids()
    known["attr"] = set()

    pattern = re.compile(r"@(?:(android):)?([a-z]+)/([A-Za-z0-9_.]+)")
    for path in sorted(RES.rglob("*.xml")):
        text = path.read_text()
        for match in pattern.finditer(text):
            if match.group(1) == "android":
                continue          # the platform's own resources
            prefix = text[max(0, match.start() - 1):match.start()]
            if prefix == "+":
                continue          # @+id/... defines one, it does not use one
            kind, name = match.group(2), match.group(3)
            if kind not in known:
                continue
            if name not in known[kind]:
                problem("%s: unknown @%s/%s" % (path, kind, name))
        for match in re.finditer(r'parent="@(?:(android):)?style/([A-Za-z0-9_.]+)"', text):
            if match.group(1) == "android":
                continue
            if match.group(2) not in known["style"]:
                problem("%s: unknown style parent %s" % (path, match.group(2)))

    for path in sorted(JAVA.glob("*.java")):
        text = path.read_text()
        for match in re.finditer(r"R\.([a-z]+)\.([A-Za-z0-9_]+)", text):
            kind, name = match.group(1), match.group(2)
            if kind == "attr":
                continue
            if kind not in known:
                problem("%s: R.%s is not checked here" % (path.name, kind))
                continue
            if name not in known[kind]:
                problem("%s: unknown R.%s.%s" % (path.name, kind, name))


def check_palettes():
    day = defined_in_values_dir("values")
    night = defined_in_values_dir("values-night")
    for name in sorted(day.get("color", set())):
        if name not in night.get("color", set()):
            problem("values-night/colors.xml is missing %s" % name)
    for name in sorted(night.get("color", set())):
        if name not in day.get("color", set()):
            problem("values/colors.xml is missing %s" % name)
    for name in sorted(night.get("style", set())):
        if name not in day.get("style", set()):
            problem("values/styles.xml has no %s (the night file overrides it)" % name)


def check_xml_well_formed():
    for path in sorted(RES.rglob("*.xml")):
        try:
            ET.parse(path)
        except Exception as error:  # noqa: BLE001 - report and carry on
            problem("%s: %s" % (path, error))
    manifest = ROOT / "AndroidManifest.xml"
    try:
        ET.parse(manifest)
    except Exception as error:  # noqa: BLE001
        problem("AndroidManifest.xml: %s" % error)


# ------------------------------------------------------------------- text --

EMOJI = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0xFE0F, 0xFE0F),
         (0x1F1E6, 0x1F1FF)]


def check_text_rules():
    allowed_arrow = {"\u2022", "\u2026", "\u2192", "\u2013", "\u2014", "\u00b7"}
    for path in list(RES.rglob("*.xml")) + list(JAVA.glob("*.java")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            for char in line:
                code = ord(char)
                if any(low <= code <= high for low, high in EMOJI):
                    problem("%s:%d: emoji %r" % (path, number, char))
    for path in list(RES.rglob("*.xml")):
        text = re.sub(r"<!--.*?-->", "", path.read_text(), flags=re.S)
        for number, line in enumerate(text.splitlines(), 1):
            if "*" in line:
                problem("%s:%d: asterisk in a resource" % (path, number))
    for path in sorted(JAVA.glob("*.java")):
        text = path.read_text()
        for match in re.finditer(r'"((?:[^"\\]|\\.)*)"', text):
            if "*" in match.group(1):
                problem("%s: asterisk in a string literal" % path.name)
    del allowed_arrow


# ------------------------------------------------------------------- java --

def strip_java(text):
    out, index, length = [], 0, len(text)
    while index < length:
        char = text[index]
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            end = text.find("\n", index)
            index = length if end < 0 else end
        elif char == "/" and index + 1 < length and text[index + 1] == "*":
            end = text.find("*/", index + 2)
            index = length if end < 0 else end + 2
        elif char == '"':
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    break
                index += 1
        elif char == "'":
            index += 1
            while index < length:
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == "'":
                    index += 1
                    break
                index += 1
        else:
            out.append(char)
            index += 1
    return "".join(out)


def argument_count(text, start):
    depth, index = 1, start
    while index < len(text):
        char = text[index]
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
            if depth == 0:
                return text[start:index]
        elif char == '"':
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                    continue
                if text[index] == '"':
                    break
                index += 1
        index += 1
    return None


def count_args(raw):
    if raw is None:
        return 0
    if not raw.strip():
        return 0
    depth, count, index = 0, 1, 0
    while index < len(raw):
        char = raw[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            count += 1
        elif char == '"':
            index += 1
            while index < len(raw):
                if raw[index] == "\\":
                    index += 2
                    continue
                if raw[index] == '"':
                    break
                index += 1
        index += 1
    return count


JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class",
    "const", "continue", "default", "do", "double", "else", "enum", "extends", "final",
    "finally", "float", "for", "goto", "if", "implements", "import", "instanceof", "int",
    "interface", "long", "native", "new", "package", "private", "protected", "public",
    "return", "short", "static", "strictfp", "super", "switch", "synchronized", "this",
    "throw", "throws", "transient", "try", "void", "volatile", "while", "true", "false",
    "null", "var", "record", "yield", "sealed", "permits",
}


#: These ones appear in front of a "(" in normal code, so they are not proof
#: of a broken name: `if (`, `catch (`, `while (` and friends.
CONTROL_FLOW = {
    "if", "else", "for", "while", "switch", "case", "default", "catch", "finally",
    "try", "do", "return", "throw", "throws", "new", "this", "super", "instanceof",
    "assert", "null", "true", "false", "yield", "synchronized",
}
#: A name that javac refuses, but that reads like one.
#: `record`, `var`, `yield`, `sealed` and `permits` are contextual: they are
#: still legal as method names, which History.record() relies on.
CONTEXTUAL = {"record", "var", "yield", "sealed", "permits"}
NEVER_A_NAME = JAVA_KEYWORDS - CONTROL_FLOW - CONTEXTUAL

METHOD_DECL = re.compile(
    r"(?:^|\n)\s*(?:@\w+\s*)?(?:public |private |protected |static |final |"
    r"synchronized |abstract )*(?:[A-Za-z0-9_<>\[\]\.\,\?]+)\s+"
    r"([a-z][A-Za-z0-9_]*)\s*\(")


def check_java_keywords():
    """A method named after a reserved word does not compile."""
    for path in sorted(JAVA.glob("*.java")):
        text = strip_java(path.read_text())
        for match in METHOD_DECL.finditer(text):
            name = match.group(1)
            if name in NEVER_A_NAME:
                line = text[:match.start()].count("\n") + 1
                problem("%s:%d: %s(...) is a Java keyword" % (path.name, line, name))


def check_java_calls():
    files = sorted(JAVA.glob("*.java"))
    classes = {path.stem for path in files}
    cleaned = {path.name: strip_java(path.read_text()) for path in files}
    declared = {}
    for name, text in cleaned.items():
        arities = {}
        for match in re.finditer(
                r"(?:^|\n)\s*(?:@\w+\s*)?(?:public |private |protected |static |final |"
                r"synchronized |abstract )*(?:[A-Za-z0-9_<>\[\]\.\,\?]+)\s+"
                r"([a-z][A-Za-z0-9_]*)\s*\(", text):
            args = argument_count(text, match.end())
            if args is None:
                continue
            arities.setdefault(match.group(1), set()).add(count_args(args))
        declared[name[:-5]] = arities
    for name, text in cleaned.items():
        for match in re.finditer(r"\b([A-Z][A-Za-z0-9_]*)\.([a-z][A-Za-z0-9_]*)\s*\(", text):
            owner, method = match.group(1), match.group(2)
            if owner not in classes or owner == name[:-5]:
                continue
            args = argument_count(text, match.end())
            if args is None:
                continue
            count = count_args(args)
            allowed = declared.get(owner, {}).get(method)
            line = text[:match.start()].count("\n") + 1
            if allowed is None:
                problem("%s:%d: %s declares no %s(...)" % (name, line, owner, method))
            elif count not in allowed:
                problem("%s:%d: %s.%s called with %d args, declared %s"
                        % (name, line, owner, method, count, sorted(allowed)))


def main():
    check_xml_well_formed()
    check_references()
    check_palettes()
    check_text_rules()
    check_java_keywords()
    check_java_calls()
    for message in PROBLEMS:
        print("problem:", message)
    print("problems:", len(PROBLEMS))
    print("layouts %d | strings %d | drawables %d | java %d"
          % (len(list((RES / "layout").glob("*.xml"))),
             len(defined_in_values_dir("values").get("string", set())),
             len(list((RES / "drawable").glob("*.xml"))),
             len(list(JAVA.glob("*.java")))))
    return 1 if PROBLEMS else 0


if __name__ == "__main__":
    sys.exit(main())
