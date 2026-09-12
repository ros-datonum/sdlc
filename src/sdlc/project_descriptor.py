"""The project descriptor `.sdlc/project.yaml` (RW-B03).

RW-B03-Project-Descriptor-Contract-v0.1 freezes one closed schema: how a
consumer repository participates in SDLC. It is identity and configuration
only. Product Requirements and lifecycle State stay in Fibery, and trusted
runtime/workspace configuration stays outside the file, so the schema has no
key for a credential, a host, a model, a policy mode or Requirement content.
Unknown keys are refused rather than kept, which is what stops such fields
becoming a shadow configuration surface.

The module is pure: values in, values out. It never opens a path, never
contacts Fibery, never reads the environment and executes nothing it stores.
A check command and a policy identifier are metadata here; RW-B04 owns the
filesystem and the bootstrap composition, and nothing in this rewrite runs
them.

Serialization is canonical and deterministic: UTF-8, LF, one final LF, frozen
key order, and JSON-compatible double-quoted string scalars, which give exact
escaping without a YAML dependency. The parser accepts that canonical form
plus a few harmless variations (CRLF endings, blank lines, a missing final
newline); anything else it refuses rather than guesses. Checks and extensions
keep the order they were given.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum

from sdlc.project_code import InvalidProjectCode, validate_project_code

DESCRIPTOR_VERSION = 1
# The descriptor is repository-relative and portable; an absolute path is not.
REPOSITORY_ROOT = "."
# Policy, check, profile and extension names share one identifier syntax.
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,63}$")
# One descriptor check is one deterministic command, so it stays on one line.
FORBIDDEN_COMMAND_CHARACTERS = ("\x00", "\r", "\n")

TOP_LEVEL_KEYS = ("version", "project", "fibery", "repository", "checks", "standards")
PROJECT_KEYS = ("name", "code")
FIBERY_KEYS = ("project_code",)
REPOSITORY_KEYS = ("root", "branch_policy", "worktree_policy", "merge_policy")
CHECK_KEYS = ("name", "command")
STANDARDS_KEYS = ("profile", "extensions")
POLICY_KEYS = ("branch_policy", "worktree_policy", "merge_policy")

ENCODING = "utf-8"
INDENT = "  "
NULL_LITERAL = "null"
EMPTY_LIST_LITERAL = "[]"
LIST_ITEM_PREFIX = "- "
KEY_SEPARATOR = ":"
INDENT_UNIT = 2
# A diagnostic names where the problem is, never the descriptor's content.
MAX_DETAIL_LENGTH = 60


class DescriptorProblem(StrEnum):
    """The class of a rejected descriptor, for bounded diagnostics."""

    INVALID_ENCODING = "invalid encoding"
    INVALID_SYNTAX = "invalid syntax"
    MISSING_KEY = "missing key"
    UNKNOWN_KEY = "unknown key"
    DUPLICATE_KEY = "duplicate key"
    INVALID_VALUE = "invalid value"
    UNSUPPORTED_VERSION = "unsupported version"
    PROJECT_CODE_MISMATCH = "project code mismatch"


class InvalidProjectDescriptor(ValueError):
    """A descriptor does not satisfy the frozen schema.

    `location` names a key path or line, never a value: a descriptor may carry
    a project name or a check command that does not belong in a diagnostic.
    """

    def __init__(self, problem: DescriptorProblem, location: str) -> None:
        super().__init__(f"{problem.value}: {location}")
        self.problem = problem
        self.location = location


@dataclass(frozen=True)
class ProjectIdentity:
    """Who the project is: its name and its already-resolved Project Code."""

    name: str
    code: str


@dataclass(frozen=True)
class FiberyMapping:
    """How the repository maps to its Fibery Project: the Code, and nothing else."""

    project_code: str


@dataclass(frozen=True)
class RepositoryConfig:
    """Repository placement and the policy names this project declares.

    The policies are metadata. Nothing in this rewrite interprets or executes
    them, and None means the descriptor declares none.
    """

    root: str = REPOSITORY_ROOT
    branch_policy: str | None = None
    worktree_policy: str | None = None
    merge_policy: str | None = None


@dataclass(frozen=True)
class ProjectCheck:
    """One named deterministic command. It is stored, never run."""

    name: str
    command: str


@dataclass(frozen=True)
class StandardsConfig:
    """The standards profile and extensions this project declares, by name."""

    profile: str | None = None
    extensions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectDescriptor:
    """One complete `.sdlc/project.yaml`, validated.

    Equality is semantic equality of every field, which is what makes a
    bootstrap rerun able to reuse an existing file without rewriting it.
    """

    version: int
    project: ProjectIdentity
    fibery: FiberyMapping
    repository: RepositoryConfig
    checks: tuple[ProjectCheck, ...]
    standards: StandardsConfig


# -- construction -----------------------------------------------------------------


def new_project_descriptor(project_name: str, project_code: str) -> ProjectDescriptor:
    """The descriptor a bootstrap generates from the two identity inputs.

    Every other value is a frozen default. No description, context, RAW source,
    repository inspection or environment value takes part.
    """
    code = _require_project_code(project_code, "project.code")
    return ProjectDescriptor(
        version=DESCRIPTOR_VERSION,
        project=ProjectIdentity(
            name=_require_project_name(project_name, "project.name"), code=code
        ),
        fibery=FiberyMapping(project_code=code),
        repository=RepositoryConfig(),
        checks=(),
        standards=StandardsConfig(),
    )


def _require_project_name(raw: str, location: str) -> str:
    if not isinstance(raw, str):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, location)
    name = raw.strip()
    if not name:
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, location)
    return name


def _require_project_code(raw: str, location: str) -> str:
    """The already-resolved Code, validated by the existing project_code rules."""
    if not isinstance(raw, str):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, location)
    try:
        return validate_project_code(raw)
    except InvalidProjectCode as error:
        raise InvalidProjectDescriptor(
            DescriptorProblem.INVALID_VALUE, location
        ) from error


# -- canonical rendering ----------------------------------------------------------


def render_descriptor(descriptor: ProjectDescriptor) -> bytes:
    """The one canonical byte representation of a descriptor."""
    repository = descriptor.repository
    lines = [
        f"version: {descriptor.version}",
        "project:",
        f"{INDENT}name: {_scalar(descriptor.project.name)}",
        f"{INDENT}code: {_scalar(descriptor.project.code)}",
        "fibery:",
        f"{INDENT}project_code: {_scalar(descriptor.fibery.project_code)}",
        "repository:",
        f"{INDENT}root: {_scalar(repository.root)}",
        *(f"{INDENT}{key}: {_scalar(getattr(repository, key))}" for key in POLICY_KEYS),
        *_render_checks(descriptor.checks),
        "standards:",
        f"{INDENT}profile: {_scalar(descriptor.standards.profile)}",
        *_render_extensions(descriptor.standards.extensions),
    ]
    return ("\n".join(lines) + "\n").encode(ENCODING)


def _render_checks(checks: tuple[ProjectCheck, ...]) -> list[str]:
    if not checks:
        return [f"checks: {EMPTY_LIST_LITERAL}"]
    lines = ["checks:"]
    for check in checks:
        lines.append(f"{INDENT}{LIST_ITEM_PREFIX}name: {_scalar(check.name)}")
        lines.append(f"{INDENT * 2}command: {_scalar(check.command)}")
    return lines


def _render_extensions(extensions: tuple[str, ...]) -> list[str]:
    if not extensions:
        return [f"{INDENT}extensions: {EMPTY_LIST_LITERAL}"]
    return [
        f"{INDENT}extensions:",
        *(
            f"{INDENT * 2}{LIST_ITEM_PREFIX}{_scalar(extension)}"
            for extension in extensions
        ),
    ]


def _scalar(value: str | None) -> str:
    """A string as a JSON-compatible literal, or the null literal."""
    if value is None:
        return NULL_LITERAL
    return json.dumps(value, ensure_ascii=False)


# -- parsing ----------------------------------------------------------------------


def parse_descriptor(content: bytes | str) -> ProjectDescriptor:
    """Parse and fully validate one descriptor, or refuse it."""
    tree = _read_document(_decode(content))
    _require_exact_keys(tree, TOP_LEVEL_KEYS, "")
    _require_version(tree["version"])
    project = _mapping(tree["project"], "project", PROJECT_KEYS)
    fibery = _mapping(tree["fibery"], "fibery", FIBERY_KEYS)
    code = _require_project_code(
        _string(project["code"], "project.code"), "project.code"
    )
    mapped = _require_project_code(
        _string(fibery["project_code"], "fibery.project_code"), "fibery.project_code"
    )
    if mapped != code:
        raise InvalidProjectDescriptor(
            DescriptorProblem.PROJECT_CODE_MISMATCH, "fibery.project_code"
        )
    return ProjectDescriptor(
        version=DESCRIPTOR_VERSION,
        project=ProjectIdentity(
            name=_require_project_name(
                _string(project["name"], "project.name"), "project.name"
            ),
            code=code,
        ),
        fibery=FiberyMapping(project_code=mapped),
        repository=_read_repository(tree["repository"]),
        checks=_read_checks(tree["checks"]),
        standards=_read_standards(tree["standards"]),
    )


def descriptor_compatible(
    existing_content: bytes | str, requested: ProjectDescriptor
) -> bool:
    """Whether existing descriptor bytes already mean exactly the requested value.

    Compatibility is semantic, so accepted formatting differences do not force
    a rewrite. An invalid descriptor is never compatible, and nothing here
    merges or patches.
    """
    try:
        return parse_descriptor(existing_content) == requested
    except InvalidProjectDescriptor:
        return False


def _require_version(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, "version")
    if value != DESCRIPTOR_VERSION:
        raise InvalidProjectDescriptor(DescriptorProblem.UNSUPPORTED_VERSION, "version")


def _read_repository(value: object) -> RepositoryConfig:
    repository = _mapping(value, "repository", REPOSITORY_KEYS)
    if _string(repository["root"], "repository.root") != REPOSITORY_ROOT:
        raise InvalidProjectDescriptor(
            DescriptorProblem.INVALID_VALUE, "repository.root"
        )
    return RepositoryConfig(
        root=REPOSITORY_ROOT,
        **{
            key: _optional_identifier(repository[key], f"repository.{key}")
            for key in POLICY_KEYS
        },
    )


def _read_checks(value: object) -> tuple[ProjectCheck, ...]:
    if not isinstance(value, list):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, "checks")
    checks: list[ProjectCheck] = []
    seen: set[str] = set()
    for position, item in enumerate(value):
        location = f"checks[{position}]"
        entry = _mapping(item, location, CHECK_KEYS)
        name = _identifier(
            _string(entry["name"], f"{location}.name"), f"{location}.name"
        )
        if name in seen:
            raise InvalidProjectDescriptor(
                DescriptorProblem.INVALID_VALUE, f"{location}.name"
            )
        seen.add(name)
        checks.append(
            ProjectCheck(
                name=name,
                command=_command(
                    _string(entry["command"], f"{location}.command"),
                    f"{location}.command",
                ),
            )
        )
    return tuple(checks)


def _read_standards(value: object) -> StandardsConfig:
    standards = _mapping(value, "standards", STANDARDS_KEYS)
    raw_extensions = standards["extensions"]
    if not isinstance(raw_extensions, list):
        raise InvalidProjectDescriptor(
            DescriptorProblem.INVALID_VALUE, "standards.extensions"
        )
    extensions: list[str] = []
    for position, item in enumerate(raw_extensions):
        location = f"standards.extensions[{position}]"
        extension = _identifier(_string(item, location), location)
        if extension in extensions:
            raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, location)
        extensions.append(extension)
    return StandardsConfig(
        profile=_optional_identifier(standards["profile"], "standards.profile"),
        extensions=tuple(extensions),
    )


def _command(value: str, location: str) -> str:
    command = value.strip()
    if not command or any(
        character in command for character in FORBIDDEN_COMMAND_CHARACTERS
    ):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, location)
    return command


def _identifier(value: str, location: str) -> str:
    if not IDENTIFIER_PATTERN.match(value):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, location)
    return value


def _optional_identifier(value: object, location: str) -> str | None:
    if value is None:
        return None
    return _identifier(_string(value, location), location)


def _string(value: object, location: str) -> str:
    if not isinstance(value, str):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, location)
    return value


def _mapping(value: object, location: str, keys: tuple[str, ...]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_VALUE, location)
    _require_exact_keys(value, keys, location)
    return value


def _require_exact_keys(
    mapping: dict[str, object], keys: tuple[str, ...], location: str
) -> None:
    """Every declared key present, and nothing undeclared kept."""
    prefix = f"{location}." if location else ""
    for key in keys:
        if key not in mapping:
            raise InvalidProjectDescriptor(
                DescriptorProblem.MISSING_KEY, f"{prefix}{key}"
            )
    for key in mapping:
        if key not in keys:
            raise InvalidProjectDescriptor(
                DescriptorProblem.UNKNOWN_KEY, f"{prefix}{_short(key)}"
            )


def _short(text: str) -> str:
    return text if len(text) <= MAX_DETAIL_LENGTH else text[:MAX_DETAIL_LENGTH] + "..."


# -- the bounded descriptor grammar -----------------------------------------------


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str


def _decode(content: bytes | str) -> str:
    if isinstance(content, str):
        return content
    try:
        return content.decode(ENCODING)
    except UnicodeDecodeError as error:
        raise InvalidProjectDescriptor(
            DescriptorProblem.INVALID_ENCODING, "document"
        ) from error


def _read_document(text: str) -> dict[str, object]:
    lines = _tokenize(text)
    if not lines or lines[0].indent != 0:
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_SYNTAX, "document")
    tree, position = _parse_mapping(lines, 0, 0)
    if position != len(lines):
        raise InvalidProjectDescriptor(
            DescriptorProblem.INVALID_SYNTAX, f"line {lines[position].number}"
        )
    return tree


def _tokenize(text: str) -> list[_Line]:
    """Significant lines only; blank lines and CRLF endings are harmless."""
    lines: list[_Line] = []
    for number, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        if not line.strip():
            continue
        if "\t" in line:
            raise InvalidProjectDescriptor(
                DescriptorProblem.INVALID_SYNTAX, f"line {number}"
            )
        indent = len(line) - len(line.lstrip(" "))
        if indent % INDENT_UNIT:
            raise InvalidProjectDescriptor(
                DescriptorProblem.INVALID_SYNTAX, f"line {number}"
            )
        lines.append(_Line(number, indent, line.strip()))
    return lines


def _parse_mapping(
    lines: list[_Line], position: int, indent: int
) -> tuple[dict[str, object], int]:
    mapping: dict[str, object] = {}
    while position < len(lines) and lines[position].indent == indent:
        line = lines[position]
        if line.text.startswith(LIST_ITEM_PREFIX):
            break
        key, separator, rest = line.text.partition(KEY_SEPARATOR)
        key = key.strip()
        if not separator or not key or " " in key:
            raise InvalidProjectDescriptor(
                DescriptorProblem.INVALID_SYNTAX, f"line {line.number}"
            )
        if key in mapping:
            raise InvalidProjectDescriptor(DescriptorProblem.DUPLICATE_KEY, _short(key))
        mapping[key], position = _parse_value(lines, position + 1, indent, rest.strip())
    return mapping, position


def _parse_value(
    lines: list[_Line], position: int, indent: int, rest: str
) -> tuple[object, int]:
    """The value of one key: an inline scalar, or the block indented under it."""
    nested = position < len(lines) and lines[position].indent > indent
    if rest:
        if nested:
            raise InvalidProjectDescriptor(
                DescriptorProblem.INVALID_SYNTAX, f"line {lines[position].number}"
            )
        return _parse_scalar(rest, lines[position - 1]), position
    if not nested:
        raise InvalidProjectDescriptor(
            DescriptorProblem.INVALID_SYNTAX, f"line {lines[position - 1].number}"
        )
    inner = lines[position].indent
    if lines[position].text.startswith(LIST_ITEM_PREFIX):
        return _parse_list(lines, position, inner)
    return _parse_mapping(lines, position, inner)


def _parse_list(
    lines: list[_Line], position: int, indent: int
) -> tuple[list[object], int]:
    items: list[object] = []
    while (
        position < len(lines)
        and lines[position].indent == indent
        and lines[position].text.startswith(LIST_ITEM_PREFIX)
    ):
        line = lines[position]
        rest = line.text[len(LIST_ITEM_PREFIX) :].strip()
        position += 1
        if rest.startswith('"') or rest in (NULL_LITERAL, EMPTY_LIST_LITERAL):
            items.append(_parse_scalar(rest, line))
            continue
        items.append(_parse_list_mapping(lines, line, rest))
        while position < len(lines) and lines[position].indent > indent:
            more, position = _parse_mapping(lines, position, lines[position].indent)
            _merge_item(items[-1], more)
    return items, position


def _parse_list_mapping(
    lines: list[_Line], line: _Line, rest: str
) -> dict[str, object]:
    key, separator, value = rest.partition(KEY_SEPARATOR)
    key = key.strip()
    if not separator or not key or " " in key or not value.strip():
        raise InvalidProjectDescriptor(
            DescriptorProblem.INVALID_SYNTAX, f"line {line.number}"
        )
    return {key: _parse_scalar(value.strip(), line)}


def _merge_item(item: object, more: dict[str, object]) -> None:
    if not isinstance(item, dict):
        raise InvalidProjectDescriptor(DescriptorProblem.INVALID_SYNTAX, "list item")
    for key, value in more.items():
        if key in item:
            raise InvalidProjectDescriptor(DescriptorProblem.DUPLICATE_KEY, _short(key))
        item[key] = value


def _parse_scalar(token: str, line: _Line) -> object:
    """Only the literals the canonical form uses: string, null, integer, empty list."""
    if token == NULL_LITERAL:
        return None
    if token == EMPTY_LIST_LITERAL:
        return []
    if token.startswith('"'):
        try:
            value = json.loads(token)
        except json.JSONDecodeError as error:
            raise InvalidProjectDescriptor(
                DescriptorProblem.INVALID_SYNTAX, f"line {line.number}"
            ) from error
        if not isinstance(value, str):
            raise InvalidProjectDescriptor(
                DescriptorProblem.INVALID_SYNTAX, f"line {line.number}"
            )
        return value
    if token.isdigit():
        return int(token)
    raise InvalidProjectDescriptor(
        DescriptorProblem.INVALID_SYNTAX, f"line {line.number}"
    )
