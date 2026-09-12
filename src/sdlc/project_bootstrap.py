"""`sdlc project bootstrap` — the one outer project setup action (RW-B04).

This module is composition, not a new capability. It prepares a consumer
repository to participate in SDLC by combining contracts and primitives that
are already frozen and verified:

    RW-B01  the closed four-path consumer manifest
    RW-B02  the static agent-guidance block and its merge policy
    RW-B03  the `.sdlc/project.yaml` descriptor schema
    project_init      the deterministic Fibery Project primitive
    requirement_add   the deterministic RAW ingestion primitive

Nothing here reinterprets exported requirements, invokes a model, starts
Requirement processing, repairs foreign state or rolls anything back. The RAW
artifact is validated early and then handed to Requirement Add exactly as it
was read; the context file is opaque bytes.

The order matters and is frozen: both inputs are read, Project identity and
the final Project Code are resolved read-only, every managed path is
preflighted, and only then is anything created. The Code resolved before the
descriptor is written is the same Code passed explicitly to Project Init, so a
later collision can never leave the descriptor describing a different Project.

Durable state is never undone. An attempt that created something and then
failed reports PARTIAL_BOOTSTRAP naming what became durable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath

from sdlc.consumer_template import (
    AGENTS_GUIDANCE_PATH,
    CLAUDE_GUIDANCE_PATH,
    CONTEXT_PATH,
    DESCRIPTOR_PATH,
    MANAGED_PATHS,
    GuidanceDisposition,
    plan_agent_guidance,
)
from sdlc.fibery_workspace import (
    FiberyError,
    FiberyWorkspace,
    ProjectRecord,
    RequirementRecord,
    RequirementWorkspace,
)
from sdlc.project_code import InvalidProjectCode, validate_project_code
from sdlc.project_descriptor import (
    InvalidProjectDescriptor,
    ProjectDescriptor,
    descriptor_compatible,
    new_project_descriptor,
    render_descriptor,
)
from sdlc.project_init import initialize_project, preflight_project_code
from sdlc.raw_source import InvalidRequirementSource, parse_raw_requirement
from sdlc.requirement_add import add_raw_requirement
from sdlc.results import AddResult, AddResultCode, InitResult, ResultCode

REQUIREMENT_TYPE_RAW = "Raw"
REQUIREMENT_INITIAL_STATE = "Draft"
ENCODING = "utf-8"
# The managed parents of the closed B01 manifest; no other directory is made.
MANAGED_PARENTS = tuple(
    sorted(
        {
            str(PurePosixPath(path).parent)
            for path in MANAGED_PATHS
            if str(PurePosixPath(path).parent) != "."
        }
    )
)
# The order B01/B04 freeze for materialization: guidance, descriptor, context.
MATERIALIZATION_ORDER = (
    AGENTS_GUIDANCE_PATH,
    CLAUDE_GUIDANCE_PATH,
    DESCRIPTOR_PATH,
    CONTEXT_PATH,
)
GUIDANCE_PATHS = (AGENTS_GUIDANCE_PATH, CLAUDE_GUIDANCE_PATH)


class BootstrapCode(StrEnum):
    """Every outcome one bootstrap attempt is allowed to report (RW-C03)."""

    PROJECT_BOOTSTRAPPED = "PROJECT_BOOTSTRAPPED"
    PROJECT_ALREADY_BOOTSTRAPPED = "PROJECT_ALREADY_BOOTSTRAPPED"
    BOOTSTRAP_CONFLICT = "BOOTSTRAP_CONFLICT"
    PARTIAL_BOOTSTRAP = "PARTIAL_BOOTSTRAP"
    BOOTSTRAP_FAILED = "BOOTSTRAP_FAILED"


NORMAL_BOOTSTRAP_OUTCOMES = frozenset(
    {BootstrapCode.PROJECT_BOOTSTRAPPED, BootstrapCode.PROJECT_ALREADY_BOOTSTRAPPED}
)


class PathPlan(StrEnum):
    """What bootstrap intends to do with one managed path."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    REUSE = "REUSE"
    CONFLICT = "CONFLICT"


class BootstrapStep(StrEnum):
    """The bounded step a failed attempt stopped at."""

    READ_INPUTS = "read inputs"
    RESOLVE_IDENTITY = "resolve project identity"
    RESOLVE_TARGET = "resolve target directory"
    PREFLIGHT_LOCAL = "preflight managed paths"
    MATERIALIZE_LOCAL = "materialize managed paths"
    VALIDATE_LOCAL = "validate local state"
    PROJECT_INIT = "initialize Fibery Project"
    VALIDATE_PROJECT = "validate Fibery Project"
    REQUIREMENT_ADD = "add initial RAW Requirement"
    VALIDATE_REQUIREMENT = "validate initial RAW Requirement"


@dataclass(frozen=True)
class ManagedPathPlan:
    """One managed path's preflighted intent and the state it was read in."""

    relative: str
    plan: PathPlan
    content: bytes | None = None
    existing: bytes | None = None
    reason: str | None = None


@dataclass(frozen=True)
class BootstrapResult:
    """The composed outcome, with bounded metadata only.

    No RAW body, project-context body, document secret, token or model output
    appears here: paths, identities and inner result codes are enough to act
    on, and everything else belongs to its own primitive's report.
    """

    code: BootstrapCode
    message: str
    target: str | None = None
    project_name: str | None = None
    project_code: str | None = None
    requirement_id: str | None = None
    local_created: tuple[str, ...] = ()
    local_updated: tuple[str, ...] = ()
    local_reused: tuple[str, ...] = ()
    target_created: bool = False
    managed_directories_created: tuple[str, ...] = ()
    project_init_code: ResultCode | None = None
    requirement_add_code: AddResultCode | None = None
    failed_step: BootstrapStep | None = None
    details: tuple[str, ...] = ()

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_BOOTSTRAP_OUTCOMES


@dataclass
class _Durable:
    """What this attempt has already made durable. Nothing is ever undone."""

    target_created: bool = False
    directories: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    project_init: InitResult | None = None
    requirement_add: AddResult | None = None
    project_created: bool = False
    requirement_created: bool = False

    @property
    def has_local_state(self) -> bool:
        return bool(
            self.target_created or self.directories or self.created or self.updated
        )

    @property
    def has_durable_state(self) -> bool:
        return self.has_local_state or self.project_created or self.requirement_created

    @property
    def changed_anything(self) -> bool:
        return self.has_durable_state


class _Stopped(Exception):
    """One bounded step could not complete; the caller classifies the outcome."""

    def __init__(
        self,
        code: BootstrapCode,
        step: BootstrapStep,
        message: str,
        details: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.step = step
        self.message = message
        self.details = details


# -- the composition ----------------------------------------------------------------


@dataclass(frozen=True)
class _Request:
    """What one bootstrap attempt was asked for, with the Name already trimmed."""

    name: str
    requirements_path: Path | str
    context_path: Path | str
    target: Path | str | None
    code: str | None
    description: str | None


def bootstrap_project(
    project_workspace: FiberyWorkspace,
    requirement_workspace: RequirementWorkspace,
    *,
    name: str,
    requirements_path: Path | str,
    context_path: Path | str,
    target: Path | str | None = None,
    code: str | None = None,
    description: str | None = None,
) -> BootstrapResult:
    """Prepare one consumer project locally and in Fibery, or report why not."""
    request = _Request(
        name=name.strip() if name else "",
        requirements_path=requirements_path,
        context_path=context_path,
        target=target,
        code=code,
        description=description,
    )
    durable = _Durable()
    state: dict[str, object] = {}
    try:
        requirement_id = _compose(
            project_workspace, requirement_workspace, request, durable, state
        )
    except _Stopped as stopped:
        return _stopped_result(stopped, durable, request.name, state)
    return _complete_result(
        durable, request.name, str(state["code"]), requirement_id, state
    )


def _compose(
    project_workspace: FiberyWorkspace,
    requirement_workspace: RequirementWorkspace,
    request: _Request,
    durable: _Durable,
    state: dict[str, object],
) -> str | None:
    """The frozen sequence: inputs, identity, local state, then Fibery."""
    if not request.name:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.READ_INPUTS,
            "Project Name is required.",
        )
    source_text, parsed = _read_requirements(request.requirements_path)
    context_bytes = _read_context(request.context_path)
    resolved_code = _resolve_identity(
        project_workspace, requirement_workspace, request.name, request.code
    )
    state["code"] = resolved_code
    directory = _resolve_target(request.target)
    state["target"] = directory
    descriptor = _requested_descriptor(request.name, resolved_code)
    plans = _preflight_local(directory, descriptor, context_bytes)
    _materialize(directory, plans, durable)
    _validate_local(directory, descriptor, context_bytes)
    project = _initialize(
        project_workspace,
        requirement_workspace,
        request.name,
        resolved_code,
        request.description,
        durable,
    )
    return _add_requirement(
        requirement_workspace, resolved_code, source_text, project, parsed, durable
    )


def _stopped_result(
    stopped: _Stopped,
    durable: _Durable,
    project_name: str,
    state: dict[str, object],
) -> BootstrapResult:
    """Classify a stopped attempt, upgrading to partial once anything is durable."""
    code = stopped.code
    if code is not BootstrapCode.PARTIAL_BOOTSTRAP and durable.changed_anything:
        code = BootstrapCode.PARTIAL_BOOTSTRAP
    return _result(
        code,
        stopped.message,
        durable,
        project_name,
        state,
        stopped.step,
        stopped.details,
    )


def _complete_result(
    durable: _Durable,
    project_name: str,
    resolved_code: str,
    requirement_id: str | None,
    state: dict[str, object],
) -> BootstrapResult:
    """A validated outcome: already bootstrapped only when nothing changed."""
    code = (
        BootstrapCode.PROJECT_BOOTSTRAPPED
        if durable.changed_anything
        else BootstrapCode.PROJECT_ALREADY_BOOTSTRAPPED
    )
    message = (
        f"Project {project_name!r} ({resolved_code}) is bootstrapped."
        if code is BootstrapCode.PROJECT_BOOTSTRAPPED
        else f"Project {project_name!r} ({resolved_code}) was already bootstrapped."
    )
    return _result(
        code, message, durable, project_name, state, None, (), requirement_id
    )


def _result(
    code: BootstrapCode,
    message: str,
    durable: _Durable,
    project_name: str,
    state: dict[str, object],
    step: BootstrapStep | None,
    details: tuple[str, ...],
    requirement_id: str | None = None,
) -> BootstrapResult:
    target = state.get("target")
    add = durable.requirement_add
    return BootstrapResult(
        code=code,
        message=message,
        target=str(target) if target is not None else None,
        project_name=project_name or None,
        project_code=state.get("code"),  # type: ignore[arg-type]
        requirement_id=requirement_id or (add.requirement_id if add else None),
        local_created=tuple(durable.created),
        local_updated=tuple(durable.updated),
        local_reused=tuple(durable.reused),
        target_created=durable.target_created,
        managed_directories_created=tuple(durable.directories),
        project_init_code=durable.project_init.code if durable.project_init else None,
        requirement_add_code=add.code if add else None,
        failed_step=step,
        details=details,
    )


# -- phase 1: inputs ----------------------------------------------------------------


def _read_requirements(path: Path | str) -> tuple[str, object]:
    """Read and validate the RAW export without transforming it in any way."""
    text = _read_text(path, "requirements")
    try:
        parsed = parse_raw_requirement(text)
    except InvalidRequirementSource as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.READ_INPUTS,
            "The RAW requirements artifact does not satisfy the export schema.",
            (str(error),),
        ) from error
    return text, parsed


def _read_text(path: Path | str, label: str) -> str:
    try:
        return Path(path).read_text(encoding=ENCODING)
    except (OSError, UnicodeDecodeError) as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.READ_INPUTS,
            f"The {label} file could not be read as UTF-8 text.",
            (type(error).__name__,),
        ) from error


def _read_context(path: Path | str) -> bytes:
    """The context is opaque: bytes in, the same bytes out."""
    try:
        return Path(path).read_bytes()
    except OSError as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.READ_INPUTS,
            "The project context file could not be read.",
            (type(error).__name__,),
        ) from error


# -- phase 2: identity ---------------------------------------------------------------


def _resolve_identity(
    project_workspace: FiberyWorkspace,
    requirement_workspace: RequirementWorkspace,
    project_name: str,
    requested: str | None,
) -> str:
    """The final Project Code, resolved read-only and frozen for this attempt."""
    try:
        existing = requirement_workspace.find_projects_by_name(project_name)
    except FiberyError as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.RESOLVE_IDENTITY,
            f"Could not look up Project {project_name!r}.",
            (str(error),),
        ) from error
    if len(existing) > 1:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT,
            BootstrapStep.RESOLVE_IDENTITY,
            f"Project Name {project_name!r} matches {len(existing)} Projects.",
            tuple(project.code or project.id for project in existing),
        )
    if existing:
        return _existing_project_code(existing[0], requested)
    resolved = preflight_project_code(project_workspace, project_name, requested)
    if isinstance(resolved, InitResult):
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT
            if resolved.code is ResultCode.PROJECT_CODE_COLLISION
            else BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.RESOLVE_IDENTITY,
            resolved.message,
            (resolved.code.value, *resolved.details),
        )
    return resolved


def _existing_project_code(project: ProjectRecord, requested: str | None) -> str:
    """Reuse the existing Project's Code; bootstrap never changes it."""
    try:
        code = validate_project_code(project.code or "")
    except InvalidProjectCode as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT,
            BootstrapStep.RESOLVE_IDENTITY,
            f"Project {project.name!r} carries a Code bootstrap cannot reuse.",
            (str(error),),
        ) from error
    if requested is None:
        return code
    try:
        wanted = validate_project_code(requested)
    except InvalidProjectCode as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.RESOLVE_IDENTITY,
            "The supplied Project Code is not valid.",
            (str(error),),
        ) from error
    if wanted != code:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT,
            BootstrapStep.RESOLVE_IDENTITY,
            f"Project {project.name!r} already uses Project Code {code}; "
            f"{wanted} was requested. Bootstrap never changes an existing Code.",
        )
    return code


def _requested_descriptor(project_name: str, resolved_code: str) -> ProjectDescriptor:
    try:
        return new_project_descriptor(project_name, resolved_code)
    except InvalidProjectDescriptor as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.RESOLVE_IDENTITY,
            "The requested descriptor identity is not valid.",
            (str(error),),
        ) from error


# -- phase 3: target -----------------------------------------------------------------


def _resolve_target(target: Path | str | None) -> Path:
    """The consumer project directory. Never followed through a symlink."""
    directory = Path.cwd() if target is None else Path(target)
    if directory.is_symlink():
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT,
            BootstrapStep.RESOLVE_TARGET,
            "The target is a symlink; bootstrap does not follow it.",
        )
    if directory.exists():
        if not directory.is_dir():
            raise _Stopped(
                BootstrapCode.BOOTSTRAP_CONFLICT,
                BootstrapStep.RESOLVE_TARGET,
                "The target exists and is not a directory.",
            )
        return directory
    parent = directory.parent
    if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT,
            BootstrapStep.RESOLVE_TARGET,
            "The target's parent is not a real directory.",
        )
    if not parent.exists():
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.RESOLVE_TARGET,
            "The target's parent directory does not exist; bootstrap creates "
            "only the final directory.",
        )
    return directory


# -- phase 4: local preflight ---------------------------------------------------------


def _preflight_local(
    directory: Path, descriptor: ProjectDescriptor, context_bytes: bytes
) -> list[ManagedPathPlan]:
    """Plan every managed path before anything is written."""
    _preflight_parents(directory)
    plans = [
        _plan_guidance(directory, AGENTS_GUIDANCE_PATH),
        _plan_guidance(directory, CLAUDE_GUIDANCE_PATH),
        _plan_descriptor(directory, descriptor),
        _plan_context(directory, context_bytes),
    ]
    conflicts = [plan for plan in plans if plan.plan is PathPlan.CONFLICT]
    if conflicts:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT,
            BootstrapStep.PREFLIGHT_LOCAL,
            "Existing project-local state conflicts with the bootstrap template; "
            "nothing was written.",
            tuple(f"{plan.relative}: {plan.reason}" for plan in conflicts),
        )
    return plans


def _preflight_parents(directory: Path) -> None:
    for relative in MANAGED_PARENTS:
        parent = directory / relative
        if parent.is_symlink():
            raise _Stopped(
                BootstrapCode.BOOTSTRAP_CONFLICT,
                BootstrapStep.PREFLIGHT_LOCAL,
                f"{relative} is a symlink; bootstrap does not follow it.",
            )
        if parent.exists() and not parent.is_dir():
            raise _Stopped(
                BootstrapCode.BOOTSTRAP_CONFLICT,
                BootstrapStep.PREFLIGHT_LOCAL,
                f"{relative} exists and is not a directory.",
            )


def _read_managed(directory: Path, relative: str) -> bytes | None:
    """The current bytes of one managed path, or None when it is absent.

    A symlink or non-regular file is refused here rather than followed.
    """
    path = directory / relative
    if path.is_symlink():
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT,
            BootstrapStep.PREFLIGHT_LOCAL,
            f"{relative} is a symlink; bootstrap does not follow it.",
        )
    if not path.exists():
        return None
    if not path.is_file():
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_CONFLICT,
            BootstrapStep.PREFLIGHT_LOCAL,
            f"{relative} exists and is not a regular file.",
        )
    try:
        return path.read_bytes()
    except OSError as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.PREFLIGHT_LOCAL,
            f"{relative} could not be read.",
            (type(error).__name__,),
        ) from error


def _plan_guidance(directory: Path, relative: str) -> ManagedPathPlan:
    """RW-B02 decides; bootstrap only maps its disposition onto a local plan."""
    existing = _read_managed(directory, relative)
    plan = plan_agent_guidance(existing)
    if plan.disposition is GuidanceDisposition.CONFLICT:
        return ManagedPathPlan(
            relative, PathPlan.CONFLICT, reason=str(plan.reason), existing=existing
        )
    if plan.disposition is GuidanceDisposition.COMPATIBLE:
        return ManagedPathPlan(relative, PathPlan.REUSE, existing=existing)
    intent = PathPlan.CREATE if existing is None else PathPlan.UPDATE
    return ManagedPathPlan(relative, intent, content=plan.content, existing=existing)


def _plan_descriptor(directory: Path, descriptor: ProjectDescriptor) -> ManagedPathPlan:
    existing = _read_managed(directory, DESCRIPTOR_PATH)
    if existing is None:
        return ManagedPathPlan(
            DESCRIPTOR_PATH, PathPlan.CREATE, content=render_descriptor(descriptor)
        )
    if descriptor_compatible(existing, descriptor):
        return ManagedPathPlan(DESCRIPTOR_PATH, PathPlan.REUSE, existing=existing)
    return ManagedPathPlan(
        DESCRIPTOR_PATH,
        PathPlan.CONFLICT,
        existing=existing,
        reason="the existing descriptor describes another project identity",
    )


def _plan_context(directory: Path, context_bytes: bytes) -> ManagedPathPlan:
    existing = _read_managed(directory, CONTEXT_PATH)
    if existing is None:
        return ManagedPathPlan(CONTEXT_PATH, PathPlan.CREATE, content=context_bytes)
    if existing == context_bytes:
        return ManagedPathPlan(CONTEXT_PATH, PathPlan.REUSE, existing=existing)
    return ManagedPathPlan(
        CONTEXT_PATH,
        PathPlan.CONFLICT,
        existing=existing,
        reason="the existing project context differs from the supplied export",
    )


# -- phase 5: materialization ---------------------------------------------------------


def _materialize(
    directory: Path, plans: list[ManagedPathPlan], durable: _Durable
) -> None:
    """Create the target, the managed directories and every planned file."""
    by_path = {plan.relative: plan for plan in plans}
    _ensure_target(directory, durable)
    _ensure_directories(directory, durable)
    for relative in MATERIALIZATION_ORDER:
        plan = by_path[relative]
        if plan.plan is PathPlan.REUSE:
            durable.reused.append(relative)
            continue
        _write_managed(directory, plan, durable)


def _ensure_target(directory: Path, durable: _Durable) -> None:
    if directory.is_dir():
        return
    try:
        directory.mkdir()
    except OSError as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.MATERIALIZE_LOCAL,
            "The target directory could not be created.",
            (type(error).__name__,),
        ) from error
    durable.target_created = True


def _ensure_directories(directory: Path, durable: _Durable) -> None:
    for relative in MANAGED_PARENTS:
        path = directory / relative
        if path.is_dir() and not path.is_symlink():
            continue
        try:
            path.mkdir()
        except OSError as error:
            raise _Stopped(
                BootstrapCode.BOOTSTRAP_FAILED,
                BootstrapStep.MATERIALIZE_LOCAL,
                f"{relative} could not be created.",
                (type(error).__name__,),
            ) from error
        durable.directories.append(relative)


def _write_managed(directory: Path, plan: ManagedPathPlan, durable: _Durable) -> None:
    """Write one planned path, after proving it is still what preflight saw."""
    path = directory / plan.relative
    content = plan.content or b""
    _recheck(path, plan)
    try:
        if plan.plan is PathPlan.CREATE:
            with open(path, "xb") as handle:
                handle.write(content)
        else:
            path.write_bytes(content)
    except OSError as error:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.MATERIALIZE_LOCAL,
            f"{plan.relative} could not be written.",
            (type(error).__name__,),
        ) from error
    if path.read_bytes() != content:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.MATERIALIZE_LOCAL,
            f"{plan.relative} did not read back as written.",
        )
    (durable.created if plan.plan is PathPlan.CREATE else durable.updated).append(
        plan.relative
    )


def _recheck(path: Path, plan: ManagedPathPlan) -> None:
    """Refuse to write over anything that changed since preflight."""
    if path.is_symlink():
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.MATERIALIZE_LOCAL,
            f"{plan.relative} became a symlink after preflight.",
        )
    if plan.plan is PathPlan.CREATE and path.exists():
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.MATERIALIZE_LOCAL,
            f"{plan.relative} appeared after preflight; it was not overwritten.",
        )
    if plan.plan is PathPlan.UPDATE and (
        not path.is_file() or path.read_bytes() != plan.existing
    ):
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.MATERIALIZE_LOCAL,
            f"{plan.relative} changed after preflight; it was not overwritten.",
        )


# -- phase 6 and 14: local validation --------------------------------------------------


def _validate_local(
    directory: Path,
    descriptor: ProjectDescriptor,
    context_bytes: bytes,
    step: BootstrapStep = BootstrapStep.VALIDATE_LOCAL,
) -> None:
    """Every managed artifact must satisfy B01, B02 and B03 before Fibery."""
    problems: list[str] = []
    for relative in MANAGED_PATHS:
        path = directory / relative
        if path.is_symlink() or not path.is_file():
            problems.append(f"{relative} is not a regular file")
    if not problems:
        problems.extend(_content_problems(directory, descriptor, context_bytes))
    if problems:
        raise _Stopped(
            BootstrapCode.BOOTSTRAP_FAILED,
            step,
            "The project-local state is not the state bootstrap requires.",
            tuple(problems),
        )


def _content_problems(
    directory: Path, descriptor: ProjectDescriptor, context_bytes: bytes
) -> list[str]:
    problems: list[str] = []
    if not descriptor_compatible(
        (directory / DESCRIPTOR_PATH).read_bytes(), descriptor
    ):
        problems.append(f"{DESCRIPTOR_PATH} does not describe this project")
    if (directory / CONTEXT_PATH).read_bytes() != context_bytes:
        problems.append(f"{CONTEXT_PATH} is not the supplied context")
    for relative in GUIDANCE_PATHS:
        plan = plan_agent_guidance((directory / relative).read_bytes())
        if plan.disposition is not GuidanceDisposition.COMPATIBLE:
            problems.append(f"{relative} does not carry the frozen SDLC block")
    return problems


# -- phase 7: the inner Project primitive ----------------------------------------------


def _initialize(
    project_workspace: FiberyWorkspace,
    requirement_workspace: RequirementWorkspace,
    project_name: str,
    resolved_code: str,
    description: str | None,
    durable: _Durable,
) -> ProjectRecord:
    """Invoke the existing Project Init with the already-resolved Code."""
    result = initialize_project(
        project_workspace,
        name=project_name,
        code=resolved_code,
        description=description,
    )
    durable.project_init = result
    durable.project_created = result.code is ResultCode.PROJECT_INITIALIZED or bool(
        result.created
    )
    if not result.is_normal:
        raise _Stopped(
            BootstrapCode.PARTIAL_BOOTSTRAP
            if result.code is ResultCode.PARTIAL_INIT or durable.changed_anything
            else BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.PROJECT_INIT,
            f"Project Init reported {result.code.value}; "
            "bootstrap changed nothing else.",
            (result.message, *result.details),
        )
    return _validate_project(
        requirement_workspace, project_workspace, project_name, resolved_code
    )


def _validate_project(
    requirement_workspace: RequirementWorkspace,
    project_workspace: FiberyWorkspace,
    project_name: str,
    resolved_code: str,
) -> ProjectRecord:
    """Exactly one Project answers to this Name and this Code, and it is one entity."""
    try:
        by_name = requirement_workspace.find_projects_by_name(project_name)
        by_code = requirement_workspace.find_project_by_code(resolved_code)
        with_code = project_workspace.count_projects_with_code(resolved_code)
    except FiberyError as error:
        raise _Stopped(
            BootstrapCode.PARTIAL_BOOTSTRAP,
            BootstrapStep.VALIDATE_PROJECT,
            "The Fibery Project could not be validated.",
            (str(error),),
        ) from error
    problems = _project_problems(
        by_name, by_code, with_code, project_name, resolved_code
    )
    if problems:
        raise _Stopped(
            BootstrapCode.PARTIAL_BOOTSTRAP,
            BootstrapStep.VALIDATE_PROJECT,
            "The Fibery Project is not the identity bootstrap requested.",
            tuple(problems),
        )
    assert by_code is not None  # _project_problems refuses None
    return by_code


def _project_problems(
    by_name: list[ProjectRecord],
    by_code: ProjectRecord | None,
    with_code: int,
    project_name: str,
    resolved_code: str,
) -> list[str]:
    problems: list[str] = []
    if len(by_name) != 1:
        problems.append(f"{len(by_name)} Projects carry the exact Name")
    if by_code is None:
        problems.append(f"no Project carries Project Code {resolved_code}")
    if with_code != 1:
        problems.append(f"{with_code} Projects carry Project Code {resolved_code}")
    if by_name and by_code is not None and by_name[0].id != by_code.id:
        problems.append("the Name and the Code resolve to different Projects")
    if by_code is not None and by_code.name != project_name:
        problems.append("the Project Name does not match the request")
    if by_code is not None and by_code.code != resolved_code:
        problems.append("the Project Code does not match the request")
    return problems


# -- phase 8 and 9: the inner Requirement primitive -------------------------------------


def _add_requirement(
    requirement_workspace: RequirementWorkspace,
    resolved_code: str,
    source_text: str,
    project: ProjectRecord,
    parsed: object,
    durable: _Durable,
) -> str | None:
    """Invoke the existing Requirement Add with the exact source text."""
    result = add_raw_requirement(
        requirement_workspace, project=resolved_code, source_text=source_text
    )
    durable.requirement_add = result
    durable.requirement_created = result.code is (
        AddResultCode.RAW_REQUIREMENT_ADDED
    ) or bool(result.created)
    if not result.is_normal:
        raise _Stopped(
            BootstrapCode.PARTIAL_BOOTSTRAP
            if result.code is AddResultCode.PARTIAL_ADD or durable.changed_anything
            else BootstrapCode.BOOTSTRAP_FAILED,
            BootstrapStep.REQUIREMENT_ADD,
            f"Requirement Add reported {result.code.value}.",
            (result.message, *result.details),
        )
    return _validate_requirement(requirement_workspace, project, parsed, result)


def _validate_requirement(
    requirement_workspace: RequirementWorkspace,
    project: ProjectRecord,
    parsed: object,
    result: AddResult,
) -> str | None:
    """The initial RAW exists once, in this Project, as Raw + Draft."""
    fingerprint = parsed.fingerprint  # type: ignore[attr-defined]
    try:
        record = requirement_workspace.find_requirement_by_fingerprint(
            project.id, fingerprint
        )
    except FiberyError as error:
        raise _Stopped(
            BootstrapCode.PARTIAL_BOOTSTRAP,
            BootstrapStep.VALIDATE_REQUIREMENT,
            "The initial RAW Requirement could not be validated.",
            (str(error),),
        ) from error
    problems = _requirement_problems(record, project, fingerprint, result)
    if problems:
        raise _Stopped(
            BootstrapCode.PARTIAL_BOOTSTRAP,
            BootstrapStep.VALIDATE_REQUIREMENT,
            "The initial RAW Requirement is not in the state bootstrap requires.",
            tuple(problems),
        )
    assert record is not None
    return record.requirement_id


def _requirement_problems(
    record: RequirementRecord | None,
    project: ProjectRecord,
    fingerprint: str,
    result: AddResult,
) -> list[str]:
    """Every way the ingested RAW differs from what bootstrap requires."""
    if record is None:
        return ["no Requirement carries the source fingerprint"]
    problems: list[str] = []
    if record.project_id != project.id:
        problems.append("the Requirement belongs to another Project")
    if record.type_name != REQUIREMENT_TYPE_RAW:
        problems.append(f"Type is {record.type_name!r}")
    if record.state != REQUIREMENT_INITIAL_STATE:
        problems.append(f"State is {record.state!r}")
    if record.source_fingerprint != fingerprint:
        problems.append("the Source Fingerprint does not match the export")
    if result.requirement_id and record.requirement_id != result.requirement_id:
        problems.append("the Requirement ID disagrees with the add result")
    return problems


__all__ = [
    "NORMAL_BOOTSTRAP_OUTCOMES",
    "BootstrapCode",
    "BootstrapResult",
    "BootstrapStep",
    "ManagedPathPlan",
    "PathPlan",
    "bootstrap_project",
]
