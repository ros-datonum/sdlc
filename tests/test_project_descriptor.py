"""RW-B03: the project descriptor schema, renderer, parser and compatibility.

Everything here is pure: bytes or values in, typed descriptor out. The suite
pins the closed schema from RW-B03-Project-Descriptor-Contract-v0.1, the exact
canonical bytes, and the fail-closed behaviour that keeps credentials,
Requirements and runtime configuration out of `.sdlc/project.yaml`.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from sdlc import project_descriptor
from sdlc.project_descriptor import (
    DESCRIPTOR_VERSION,
    REPOSITORY_ROOT,
    DescriptorProblem,
    FiberyMapping,
    InvalidProjectDescriptor,
    ProjectCheck,
    ProjectDescriptor,
    ProjectIdentity,
    RepositoryConfig,
    StandardsConfig,
    descriptor_compatible,
    new_project_descriptor,
    parse_descriptor,
    render_descriptor,
)

NAME = "Example Project"
CODE = "EXAMPL"

DEFAULT_YAML = b"""version: 1
project:
  name: "Example Project"
  code: "EXAMPL"
fibery:
  project_code: "EXAMPL"
repository:
  root: "."
  branch_policy: null
  worktree_policy: null
  merge_policy: null
checks: []
standards:
  profile: null
  extensions: []
"""

POPULATED_YAML = b"""version: 1
project:
  name: "Example Project"
  code: "EXAMPL"
fibery:
  project_code: "EXAMPL"
repository:
  root: "."
  branch_policy: "trunk"
  worktree_policy: null
  merge_policy: "squash"
checks:
  - name: "test"
    command: "uv run pytest -q"
  - name: "lint"
    command: "uv run ruff check ."
standards:
  profile: "python"
  extensions:
    - "security"
    - "api"
"""


def default() -> ProjectDescriptor:
    return new_project_descriptor(NAME, CODE)


def populated() -> ProjectDescriptor:
    return ProjectDescriptor(
        version=DESCRIPTOR_VERSION,
        project=ProjectIdentity(name=NAME, code=CODE),
        fibery=FiberyMapping(project_code=CODE),
        repository=RepositoryConfig(
            root=REPOSITORY_ROOT, branch_policy="trunk", merge_policy="squash"
        ),
        checks=(
            ProjectCheck(name="test", command="uv run pytest -q"),
            ProjectCheck(name="lint", command="uv run ruff check ."),
        ),
        standards=StandardsConfig(profile="python", extensions=("security", "api")),
    )


def replaced(original: str, replacement: str) -> bytes:
    text = DEFAULT_YAML.decode("utf-8")
    assert original in text, original
    return text.replace(original, replacement).encode("utf-8")


def problem_of(content: bytes | str) -> DescriptorProblem:
    with pytest.raises(InvalidProjectDescriptor) as raised:
        parse_descriptor(content)
    return raised.value.problem


# -- default generation ------------------------------------------------------------


def test_the_default_descriptor_is_exactly_the_frozen_bootstrap_value():
    descriptor = default()

    assert descriptor == ProjectDescriptor(
        version=1,
        project=ProjectIdentity(name=NAME, code=CODE),
        fibery=FiberyMapping(project_code=CODE),
        repository=RepositoryConfig(
            root=".", branch_policy=None, worktree_policy=None, merge_policy=None
        ),
        checks=(),
        standards=StandardsConfig(profile=None, extensions=()),
    )


@pytest.mark.parametrize("supplied", ["  Example Project  ", "\tExample Project\n"])
def test_the_project_name_is_trimmed(supplied):
    assert new_project_descriptor(supplied, CODE).project.name == NAME


@pytest.mark.parametrize("supplied", ["", "   ", "\n\t "])
def test_a_blank_project_name_is_refused(supplied):
    with pytest.raises(InvalidProjectDescriptor) as raised:
        new_project_descriptor(supplied, CODE)
    assert raised.value.problem is DescriptorProblem.INVALID_VALUE


@pytest.mark.parametrize(
    ("supplied", "stored"), [("exampl", CODE), ("  exampl  ", CODE)]
)
def test_the_project_code_follows_the_existing_validator(supplied, stored):
    descriptor = new_project_descriptor(NAME, supplied)

    assert descriptor.project.code == stored
    assert descriptor.fibery.project_code == stored


@pytest.mark.parametrize("supplied", ["", "1SDLC", "SD LC", "SD-LC", "S" * 13])
def test_an_invalid_project_code_is_refused(supplied):
    with pytest.raises(InvalidProjectDescriptor):
        new_project_descriptor(NAME, supplied)


def test_generation_is_deterministic():
    assert default() == default()
    assert render_descriptor(default()) == render_descriptor(default())


# -- canonical rendering -----------------------------------------------------------


def test_the_default_descriptor_renders_the_exact_canonical_bytes():
    assert render_descriptor(default()) == DEFAULT_YAML


def test_a_populated_descriptor_renders_the_exact_canonical_bytes():
    assert render_descriptor(populated()) == POPULATED_YAML


def test_the_rendering_ends_with_exactly_one_newline():
    rendered = render_descriptor(default())

    assert rendered.endswith(b"\n")
    assert not rendered.endswith(b"\n\n")
    assert b"\r" not in rendered


@pytest.mark.parametrize(
    "name",
    [
        "Проект",
        'Quote " backslash \\ end',
        "Tab\tinside",
        "Ünicode — dash",
    ],
)
def test_unusual_project_names_round_trip_exactly(name):
    descriptor = new_project_descriptor(name, CODE)

    assert parse_descriptor(render_descriptor(descriptor)) == descriptor


def test_checks_and_extensions_keep_the_order_they_were_given():
    reversed_order = ProjectDescriptor(
        version=DESCRIPTOR_VERSION,
        project=ProjectIdentity(name=NAME, code=CODE),
        fibery=FiberyMapping(project_code=CODE),
        repository=RepositoryConfig(),
        checks=(
            ProjectCheck(name="lint", command="uv run ruff check ."),
            ProjectCheck(name="test", command="uv run pytest -q"),
        ),
        standards=StandardsConfig(profile=None, extensions=("api", "security")),
    )

    rendered = render_descriptor(reversed_order).decode("utf-8")

    assert rendered.index('"lint"') < rendered.index('"test"')
    assert rendered.index('"api"') < rendered.index('"security"')
    assert parse_descriptor(rendered) == reversed_order


# -- parsing -----------------------------------------------------------------------


def test_the_canonical_default_parses_back():
    assert parse_descriptor(DEFAULT_YAML) == default()


def test_a_populated_descriptor_parses_back():
    assert parse_descriptor(POPULATED_YAML) == populated()


def test_text_and_bytes_are_both_accepted():
    assert parse_descriptor(DEFAULT_YAML.decode("utf-8")) == default()


ACCEPTED_FORMATTING = {
    "crlf": DEFAULT_YAML.replace(b"\n", b"\r\n"),
    "no-final-newline": DEFAULT_YAML.rstrip(b"\n"),
    "blank-lines": DEFAULT_YAML.replace(b"fibery:", b"\nfibery:"),
}


@pytest.mark.parametrize(
    "content", ACCEPTED_FORMATTING.values(), ids=ACCEPTED_FORMATTING.keys()
)
def test_harmless_formatting_variations_are_accepted_deterministically(content):
    assert parse_descriptor(content) == default()


def test_invalid_utf8_is_refused():
    assert problem_of(b"version: 1\nproject:\n  name: \xff\n") is (
        DescriptorProblem.INVALID_ENCODING
    )


SYNTAX_ERRORS = {
    "empty": b"",
    "not-a-mapping": b'- "a"\n',
    "tab-indent": DEFAULT_YAML.replace(b"  name:", b"\tname:"),
    "odd-indent": DEFAULT_YAML.replace(b"  name:", b"   name:"),
    "missing-colon": DEFAULT_YAML.replace(b"checks: []", b"checks"),
    "unquoted-scalar": DEFAULT_YAML.replace(b'"Example Project"', b"Example Project"),
    "comment": b"# a comment\n" + DEFAULT_YAML,
    "unterminated-string": DEFAULT_YAML.replace(b'"EXAMPL"\n', b'"EXAMPL\n'),
    "value-and-block": DEFAULT_YAML.replace(b"project:", b'project: "x"'),
    "empty-value": DEFAULT_YAML.replace(b"checks: []", b"checks:"),
}


@pytest.mark.parametrize("content", SYNTAX_ERRORS.values(), ids=SYNTAX_ERRORS.keys())
def test_malformed_syntax_is_refused_rather_than_guessed(content):
    assert problem_of(content) in (
        DescriptorProblem.INVALID_SYNTAX,
        DescriptorProblem.INVALID_ENCODING,
    )


@pytest.mark.parametrize(
    "group",
    ["version: 1\n", "project:", "fibery:", "repository:", "checks: []", "standards:"],
)
def test_a_missing_mandatory_group_is_refused(group):
    text = DEFAULT_YAML.decode("utf-8")
    if group.endswith(":"):
        # drop the group header and its indented block
        lines = text.split("\n")
        start = lines.index(group)
        end = start + 1
        while end < len(lines) and lines[end].startswith(" "):
            end += 1
        remaining = "\n".join(lines[:start] + lines[end:])
    else:
        remaining = text.replace(group, "")

    assert problem_of(remaining) is DescriptorProblem.MISSING_KEY


MISSING_NESTED = {
    "project.name": '  name: "Example Project"\n',
    "project.code": '  code: "EXAMPL"\n',
    "repository.root": '  root: "."\n',
    "repository.branch_policy": "  branch_policy: null\n",
    "standards.profile": "  profile: null\n",
    "standards.extensions": "  extensions: []\n",
}


@pytest.mark.parametrize("line", MISSING_NESTED.values(), ids=MISSING_NESTED.keys())
def test_a_missing_nested_key_is_refused(line):
    assert problem_of(replaced(line, "")) is DescriptorProblem.MISSING_KEY


def test_the_single_key_fibery_group_refuses_both_of_its_failure_shapes():
    """Replacing the only key leaves the group present but incomplete; removing
    it leaves a group header with no block, which the grammar refuses."""
    substituted = replaced('  project_code: "EXAMPL"\n', '  other: "EXAMPL"\n')
    emptied = replaced('  project_code: "EXAMPL"\n', "")

    assert problem_of(substituted) is DescriptorProblem.MISSING_KEY
    assert problem_of(emptied) is DescriptorProblem.INVALID_SYNTAX


UNKNOWN_KEYS = {
    "top-level": ("checks: []\n", 'checks: []\nextra: "x"\n'),
    "nested-project": ('  code: "EXAMPL"\n', '  code: "EXAMPL"\n  owner: "x"\n'),
    "nested-repository": ('  root: "."\n', '  root: "."\n  remote: "x"\n'),
    "nested-standards": ("  profile: null\n", '  profile: null\n  registry: "x"\n'),
}


@pytest.mark.parametrize(
    ("original", "replacement"), UNKNOWN_KEYS.values(), ids=UNKNOWN_KEYS.keys()
)
def test_an_unknown_key_is_refused(original, replacement):
    assert problem_of(replaced(original, replacement)) is DescriptorProblem.UNKNOWN_KEY


DUPLICATE_KEYS = {
    "top-level": ("checks: []\n", "checks: []\nchecks: []\n"),
    "nested": ('  code: "EXAMPL"\n', '  code: "EXAMPL"\n  code: "EXAMPL"\n'),
    "check-item": (
        '  - name: "test"\n    command: "uv run pytest -q"\n',
        '  - name: "test"\n    command: "uv run pytest -q"\n    command: "x"\n',
    ),
}


@pytest.mark.parametrize(
    ("original", "replacement"), DUPLICATE_KEYS.values(), ids=DUPLICATE_KEYS.keys()
)
def test_a_duplicate_key_is_refused(original, replacement):
    source = POPULATED_YAML if "- name:" in original else DEFAULT_YAML
    text = source.decode("utf-8")
    assert original in text
    assert problem_of(text.replace(original, replacement)) is (
        DescriptorProblem.DUPLICATE_KEY
    )


WRONG_TYPES = {
    "project-scalar": (
        'project:\n  name: "Example Project"\n  code: "EXAMPL"\n',
        'project: "x"\n',
    ),
    "checks-scalar": ("checks: []\n", 'checks: "x"\n'),
    "extensions-scalar": ("  extensions: []\n", '  extensions: "x"\n'),
    "name-null": ('  name: "Example Project"\n', "  name: null\n"),
    "version-string": ("version: 1\n", 'version: "1"\n'),
    "check-item-scalar": ("checks: []\n", 'checks:\n  - "test"\n'),
}


@pytest.mark.parametrize(
    ("original", "replacement"), WRONG_TYPES.values(), ids=WRONG_TYPES.keys()
)
def test_a_wrong_value_type_is_refused(original, replacement):
    assert problem_of(replaced(original, replacement)) is (
        DescriptorProblem.INVALID_VALUE
    )


@pytest.mark.parametrize("version", ["0", "2", "11"])
def test_an_unsupported_version_is_refused(version):
    assert problem_of(replaced("version: 1\n", f"version: {version}\n")) is (
        DescriptorProblem.UNSUPPORTED_VERSION
    )


INVALID_VALUES = {
    "blank-name": ('  name: "Example Project"\n', '  name: "   "\n'),
    "invalid-code": ('  code: "EXAMPL"\n', '  code: "1BAD"\n'),
    "absolute-root": ('  root: "."\n', '  root: "/srv/project"\n'),
    "relative-root": ('  root: "."\n', '  root: "./sub"\n'),
    "invalid-policy": ("  branch_policy: null\n", '  branch_policy: "-bad"\n'),
    "invalid-profile": ("  profile: null\n", '  profile: "9bad"\n'),
    "invalid-extension": ("  extensions: []\n", '  extensions:\n    - "bad space"\n'),
    "duplicate-extension": (
        "  extensions: []\n",
        '  extensions:\n    - "security"\n    - "security"\n',
    ),
    "invalid-check-name": (
        "checks: []\n",
        'checks:\n  - name: "9bad"\n    command: "x"\n',
    ),
    "blank-command": (
        "checks: []\n",
        'checks:\n  - name: "test"\n    command: "   "\n',
    ),
    "multiline-command": (
        "checks: []\n",
        'checks:\n  - name: "test"\n    command: "a\\nb"\n',
    ),
    "nul-command": (
        "checks: []\n",
        'checks:\n  - name: "test"\n    command: "a\\u0000b"\n',
    ),
    "duplicate-check-name": (
        "checks: []\n",
        'checks:\n  - name: "test"\n    command: "a"\n  - name: "test"\n    command: "b"\n',
    ),
}


@pytest.mark.parametrize(
    ("original", "replacement"), INVALID_VALUES.values(), ids=INVALID_VALUES.keys()
)
def test_an_invalid_value_is_refused(original, replacement):
    assert problem_of(replaced(original, replacement)) is (
        DescriptorProblem.INVALID_VALUE
    )


def test_a_mismatched_fibery_project_code_is_refused():
    content = replaced('  project_code: "EXAMPL"\n', '  project_code: "OTHER"\n')

    assert problem_of(content) is DescriptorProblem.PROJECT_CODE_MISMATCH


def test_a_diagnostic_names_the_location_and_never_the_content():
    secret_name = "Project Apollo: acquire the competitor"
    content = replaced(
        '  name: "Example Project"\n', f'  name: "{secret_name}"\n  x: 1\n'
    )

    with pytest.raises(InvalidProjectDescriptor) as raised:
        parse_descriptor(content)

    assert secret_name not in str(raised.value)
    assert "competitor" not in raised.value.location
    assert len(raised.value.location) <= 80


# -- roundtrip ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "descriptor", [default(), populated()], ids=["default", "populated"]
)
def test_parse_of_render_returns_the_same_value(descriptor):
    assert parse_descriptor(render_descriptor(descriptor)) == descriptor


@pytest.mark.parametrize(
    "descriptor", [default(), populated()], ids=["default", "populated"]
)
def test_render_of_parse_of_render_is_byte_stable(descriptor):
    rendered = render_descriptor(descriptor)

    assert render_descriptor(parse_descriptor(rendered)) == rendered


def test_unchanged_inputs_generate_byte_identical_descriptors():
    assert render_descriptor(new_project_descriptor(NAME, CODE)) == render_descriptor(
        new_project_descriptor(f"  {NAME} ", "exampl")
    )


# -- semantic compatibility --------------------------------------------------------


def test_the_same_canonical_descriptor_is_compatible():
    assert descriptor_compatible(DEFAULT_YAML, default())


@pytest.mark.parametrize(
    "content", ACCEPTED_FORMATTING.values(), ids=ACCEPTED_FORMATTING.keys()
)
def test_accepted_formatting_differences_stay_compatible(content):
    assert descriptor_compatible(content, default())
    assert content != DEFAULT_YAML, "compatible bytes need not be canonical bytes"


INCOMPATIBLE = {
    "invalid": b"version: 2\n",
    "different-name": replaced('  name: "Example Project"\n', '  name: "Other"\n'),
    "different-code": DEFAULT_YAML.replace(b"EXAMPL", b"OTHER"),
    "different-policy": replaced(
        "  branch_policy: null\n", '  branch_policy: "trunk"\n'
    ),
    "different-check": replaced(
        "checks: []\n", 'checks:\n  - name: "test"\n    command: "uv run pytest -q"\n'
    ),
    "different-standards": replaced("  profile: null\n", '  profile: "python"\n'),
}


@pytest.mark.parametrize("content", INCOMPATIBLE.values(), ids=INCOMPATIBLE.keys())
def test_any_semantic_difference_or_invalidity_conflicts(content):
    assert not descriptor_compatible(content, default())


def test_compatibility_never_rewrites_or_merges():
    """A compatible file is reused as it is; the decision is a pure comparison."""
    existing = ACCEPTED_FORMATTING["crlf"]

    assert descriptor_compatible(existing, default())
    assert existing == DEFAULT_YAML.replace(b"\n", b"\r\n"), "input is untouched"


# -- the closed authority surface ---------------------------------------------------

SHADOW_KEYS = [
    'fibery_token: "x"',
    'token: "x"',
    'api_key: "x"',
    'password: "x"',
    'secret: "x"',
    'oauth: "x"',
    'model: "x"',
    'model_provider: "x"',
    'provider_endpoint: "x"',
    'approval_policy: "x"',
    'permission_mode: "x"',
    'sandbox_mode: "x"',
    'edit_mode: "x"',
    'requirements: "x"',
    'raw_source: "x"',
    'state: "x"',
    'processing_status: "x"',
    'architecture: "x"',
    'epics: "x"',
    'tasks: "x"',
]


@pytest.mark.parametrize("line", SHADOW_KEYS)
def test_every_shadow_configuration_key_fails_as_unknown(line):
    assert problem_of(replaced("checks: []\n", f"checks: []\n{line}\n")) is (
        DescriptorProblem.UNKNOWN_KEY
    )


@pytest.mark.parametrize(
    "line",
    [
        '  host: "example.fibery.io"',
        '  space_id: "uuid"',
        '  token: "secret"',
        '  project_uuid: "uuid"',
    ],
)
def test_the_fibery_group_accepts_nothing_but_the_project_code(line):
    content = replaced(
        '  project_code: "EXAMPL"\n', f'  project_code: "EXAMPL"\n{line}\n'
    )

    assert problem_of(content) is DescriptorProblem.UNKNOWN_KEY


def test_the_schema_declares_exactly_the_six_frozen_groups():
    assert project_descriptor.TOP_LEVEL_KEYS == (
        "version",
        "project",
        "fibery",
        "repository",
        "checks",
        "standards",
    )


def test_generation_accepts_no_input_beyond_name_and_code():
    parameters = new_project_descriptor.__code__.co_varnames[
        : new_project_descriptor.__code__.co_argcount
    ]

    assert parameters == ("project_name", "project_code")


# -- purity --------------------------------------------------------------------------


def test_the_module_imports_only_the_standard_library_and_project_code():
    tree = ast.parse(
        pathlib.Path(project_descriptor.__file__).read_text(encoding="utf-8")
    )
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    imported |= {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert imported <= {
        "__future__",
        "json",
        "re",
        "dataclasses",
        "enum",
        "sdlc.project_code",
    }
