"""The boundary between deterministic `project init` behaviour and Fibery.

Everything the command needs from Fibery is expressed here. `project_init`
depends only on this protocol, so its behaviour is testable without a live
workspace.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class FiberyError(Exception):
    """Any failure while talking to Fibery."""


@dataclass(frozen=True)
class ProjectRecord:
    """A Project entity as read back from Fibery.

    `public_id` is Fibery's `fibery/public-id`, which is what a Document's
    container-entity-id actually carries; `id` is the entity uuid. The two are
    different values and neither is derivable from the other. It defaults to
    empty so existing positional constructions cannot be silently re-bound, and
    the live adapter refuses a Project row that carries no public id rather than
    handing one back.
    """

    id: str
    name: str
    code: str | None
    state: str | None
    public_id: str = ""


@dataclass(frozen=True)
class RequirementRecord:
    """A Requirement entity as read back from Fibery."""

    id: str
    public_id: str
    requirement_id: str | None
    title: str | None
    type_name: str | None
    state: str | None
    revision: int | None
    project_id: str | None
    source_fingerprint: str | None
    # The Requirement's Category (FUNCTIONAL, NON_FUNCTIONAL, CONSTRAINT), read
    # from the existing Fibery Field. None means the Field is unset or absent
    # from the schema; it is never inferred from Type, ID or Title.
    category: str | None = None
    # The Processing Status option name (RW-C04 section 4), read from the
    # single-select Field when the workspace has one. None means the Field is
    # unset, absent, or not a single-select; only the worker runner needs it.
    processing_status: str | None = None


@dataclass(frozen=True)
class DocumentNode:
    """One Fibery Document (a View of type "document").

    `entity_public_id` is the public id of the entity it is attached to, which
    is how Fibery models the Documents field. `folder_id` is the legacy
    `fibery/Folder` value: Documents created before the Type/State navigation
    model still carry one, new ones carry none, and no lifecycle behaviour
    reads it. Both are None when Fibery has not set them.
    """

    id: str
    name: str
    folder_id: str | None
    entity_public_id: str | None
    secret: str | None = None
    parent_document_id: str | None = None


@dataclass(frozen=True)
class DocumentPlacement:
    """Where one Document sits, as the Views API reports it.

    Added beside `DocumentNode` rather than widening it: three frozen
    capabilities already consume `DocumentNode`, and TSA root validation needs
    `container_entity_type`, which that record deliberately does not expose
    (TSA-C01 implementation spec 2.2.1).

    Every field is read straight from the view. A missing container field stays
    `None` and is never inferred: an unset container is a refusal, not a pass.
    """

    document_id: str
    secret: str | None
    name: str
    container_entity_type: str | None
    container_entity_id: str | None
    parent_document_id: str | None


def is_valid_root_placement(
    placement: DocumentPlacement,
    expected_project_type_id: str,
    expected_project_public_id: str,
) -> bool:
    """Whether a Document is a TSA root: contained by the Project, no parent.

    All four conditions of 2.2.1 must hold. A Document contained by the Project
    *and* nested under another Document is not a root, and an unset container
    field is a refusal rather than a pass.
    """
    return (
        bool(placement.container_entity_type)
        and bool(placement.container_entity_id)
        and placement.container_entity_type == expected_project_type_id
        and placement.container_entity_id == expected_project_public_id
        and placement.parent_document_id is None
    )


def is_valid_child_placement(
    child: DocumentPlacement,
    architecture_root: DocumentPlacement,
    expected_architecture_document_id: str,
    expected_project_type_id: str,
    expected_project_public_id: str,
) -> bool:
    """Whether a Document is a TSA child of the given Architecture root.

    Two ordered steps (2.2.1): the child names the Architecture Document as its
    parent, and that parent is itself a valid root of the expected Project. The
    child's *own* container fields are never compared against the Project — a
    nested view carries whatever container the Views API reports for a child
    page, and the containment guarantee runs through the root.

    The caller supplies the root placement, so this predicate performs no IO and
    cannot be satisfied by a child alone.
    """
    return (
        child.parent_document_id == expected_architecture_document_id
        and architecture_root.document_id == expected_architecture_document_id
        and is_valid_root_placement(
            architecture_root, expected_project_type_id, expected_project_public_id
        )
    )


class FiberyWorkspace(Protocol):
    """Operations `project init` performs against a Fibery workspace."""

    def find_project_by_name(self, name: str) -> ProjectRecord | None:
        """Return the Project with this exact Name, or None."""

    def count_projects_with_code(self, code: str) -> int:
        """Count Projects carrying this Code.

        Implementations may saturate the count: callers only distinguish
        none, exactly one, and more than one.
        """

    def create_project(self, name: str, code: str) -> str:
        """Create the Project entity and return its id."""

    def set_project_state(self, project_id: str, state: str) -> None:
        """Set the Project workflow state by state name."""

    def set_project_description(self, project_id: str, description: str) -> None:
        """Replace the Project Description rich text with Markdown."""

    def read_project(self, project_id: str) -> ProjectRecord | None:
        """Read a Project entity back by id."""


class RequirementWorkspace(Protocol):
    """Operations `project requirement add` performs against Fibery.

    Kept separate from FiberyWorkspace so the frozen `project init` contract
    stays exactly as reviewed.
    """

    def find_project_by_code(self, code: str) -> ProjectRecord | None:
        """Return the Project with this exact Code, or None."""

    def find_projects_by_name(self, name: str) -> list[ProjectRecord]:
        """Every Project with this exact Name, so ambiguity can be detected."""

    def find_requirement_by_fingerprint(
        self, project_id: str, fingerprint: str
    ) -> RequirementRecord | None:
        """The Requirement already ingested from this source, if any."""

    def create_requirement(
        self, project_id: str, title: str, revision: int, fingerprint: str
    ) -> RequirementRecord:
        """Create the Requirement entity and return it, including its public id.

        The Requirement ID is not supplied: it is derived from the public id
        Fibery allocates here, then written by set_requirement_id.
        """

    def set_requirement_id(self, entity_id: str, requirement_id: str) -> None:
        """Write the derived Requirement ID onto the created entity."""

    def set_requirement_type(self, requirement_id: str, type_name: str) -> None:
        """Set the Type single-select by option name."""

    def set_requirement_state(self, requirement_id: str, state: str) -> None:
        """Set the Requirement workflow state by state name."""

    def read_requirement(self, requirement_id: str) -> RequirementRecord | None:
        """Read a Requirement entity back by id."""

    def create_requirement_document(
        self, name: str, requirement_public_id: str
    ) -> DocumentNode:
        """Create the Root Document contained by the Requirement, with no Folder."""

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        """Read one Document back by its own id, or None."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Every Document attached to this Requirement, for the count-of-1 check."""

    def write_document_content(self, secret: str, markdown: str) -> None:
        """Replace a Document's Markdown content."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content back."""


class ArchitectureWorkspace(Protocol):
    """Operations the Technical Solution Architecture cycle performs on Fibery.

    Kept separate from the Requirement protocols so their frozen contracts stay
    exactly as reviewed. It is not a generic entity-document framework: it adds
    only what TSA-C01 section 2 requires.

    Nothing here caches. Every placement read goes to Fibery, because a caller
    must be able to revalidate immediately before each mutation.
    """

    @property
    def lock_scope(self) -> str:
        """Stable identity of the workspace, for the cycle's execution lock."""

    def read_project(self, project_id: str) -> ProjectRecord | None:
        """Read a Project entity back by id, including its public id."""

    def create_project_document(
        self, document_id: str, name: str, project_public_id: str
    ) -> DocumentNode:
        """Create a Document contained by the Project, at the caller's own id."""

    def create_tsa_child_document(
        self, document_id: str, name: str, parent_document_id: str
    ) -> DocumentNode:
        """Create a Document nested under another, at the caller's own id."""

    def create_child_document(self, name: str, parent_document_id: str) -> DocumentNode:
        """Create a Document nested under another, at a generated id.

        The reused legacy creator. TSA itself never calls it: a deterministic
        cycle uses `create_tsa_child_document`, and the two stay distinct.
        """

    def documents_attached_to_project(
        self, project_public_id: str
    ) -> list[DocumentPlacement]:
        """Every Document contained by this Project, with placement metadata."""

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        """Documents nested directly under this one, as `DocumentNode`."""

    def child_placements(self, parent_document_id: str) -> list[DocumentPlacement]:
        """Every Document nested directly under this one, with placement."""

    def resolve_placement(self, document_id: str) -> DocumentPlacement | None:
        """One Document's placement by its own id, or None.

        Reports what Fibery holds. It makes no ownership judgement: deciding
        whether that placement is admissible is the caller's, through the
        predicates above.
        """

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        """Read one Document back by its own id, or None."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content."""

    def write_document_content(self, secret: str, markdown: str) -> None:
        """Replace a Document's Markdown content."""


@dataclass(frozen=True)
class RequirementRelations:
    """The forward relations a Requirement already has.

    Only the forward sides are modelled: Fibery maintains `Blocks` and
    `Impacted By` automatically because each pair shares one relation, so
    reading them separately would report the same edges twice.

    Requirement IDs rather than entity ids, because the reviewer compares them
    against proposals that name Requirement IDs and must never see a Fibery
    identifier.
    """

    depends_on: tuple[str, ...] = ()
    affects: tuple[str, ...] = ()


class RawProcessorWorkspace(Protocol):
    """Operations the RAW Requirement Processor performs against Fibery.

    Kept separate from the frozen capabilities' protocols so their reviewed
    contracts stay exactly as they are.
    """

    @property
    def lock_scope(self) -> str:
        """Stable identity of the workspace, for the per-RAW execution lock.

        Host plus Space id: the same in every shell, working directory and
        clone that talks to the same workspace. Never a token or a title.
        """

    def read_requirement(self, entity_id: str) -> RequirementRecord | None:
        """Read one Requirement entity by id."""

    def find_requirement_by_requirement_id(
        self, requirement_id: str
    ) -> RequirementRecord | None:
        """Resolve a Requirement by its human Requirement ID."""

    def read_project(self, project_id: str) -> ProjectRecord | None:
        """Read the Project a Requirement belongs to."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Documents attached to this Requirement entity."""

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        """Documents nested directly under this Document."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content."""

    def write_document_content(self, secret: str, markdown: str) -> None:
        """Replace a Document's Markdown content."""

    def create_child_document(self, name: str, parent_document_id: str) -> DocumentNode:
        """Create a Document nested under another Document."""

    def standard_requirements_in_project(
        self, project_id: str
    ) -> list[RequirementRecord]:
        """Existing Standard Requirements, for duplicate/conflict findings."""

    def derived_from(self, entity_id: str) -> list[RequirementRecord]:
        """The Requirements this one derives from, through Derived From."""

    def requirement_relations(self, entity_id: str) -> RequirementRelations:
        """The Depends On and Affects edges this Requirement already has.

        Read-only. Nothing in this protocol writes a dependency or impact
        relation, which is what makes it structurally impossible for review to
        alter the shared dependency graph.
        """

    def create_requirement_with_id(
        self,
        entity_id: str,
        project_id: str,
        title: str,
        revision: int,
        category: str,
    ) -> RequirementRecord:
        """Create a Standard Requirement at an exact, caller-chosen entity id.

        Fibery rejects a second create at the same id, which is what makes a
        retry safe.
        """

    def set_requirement_id(self, entity_id: str, requirement_id: str) -> None:
        """Write the derived Requirement ID onto the entity."""

    def set_requirement_type(self, entity_id: str, type_name: str) -> None:
        """Set the Type single-select by option name."""

    def set_requirement_state(self, entity_id: str, state: str) -> None:
        """Set the Requirement workflow state by state name."""

    def add_derived_from(self, entity_id: str, raw_entity_id: str) -> None:
        """Link a Standard Requirement to the RAW it came from.

        Fibery populates the inverse `Produces` automatically. Collections
        cannot be written during entity creation, so this is a separate call.
        """

    def create_requirement_document(
        self, name: str, requirement_public_id: str
    ) -> DocumentNode:
        """Create a Root Document contained by a Requirement, with no Folder."""

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        """Read one Document back by id."""


class ReadyDecisionWorkspace(Protocol):
    """Operations the Standard Requirement Ready Decision performs against Fibery.

    Deliberately narrower than `RawProcessorWorkspace`: there is no way to write
    a Document, create one, or touch a relation through this protocol, which is
    what makes it structurally impossible for a human decision to alter the
    evidence it was made on. The single write is the workflow State.
    """

    def read_requirement(self, entity_id: str) -> RequirementRecord | None:
        """Read one Requirement entity by id."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Documents attached to this Requirement entity."""

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        """Documents nested directly under this Document."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content."""

    def set_requirement_state(self, entity_id: str, state: str) -> None:
        """Move the Requirement's workflow State."""


class ApplyWorkspace(Protocol):
    """Operations the Standard Requirement Apply performs against Fibery.

    Confined to what deterministic application needs. There is no way to
    write a Document body, create or move a Document, remove a relation or
    touch `Revision` through this protocol. The two writes are additive
    relation membership and the workflow State.
    """

    def read_requirement(self, entity_id: str) -> RequirementRecord | None:
        """Read one Requirement entity by id."""

    def find_requirements_by_requirement_id(
        self, requirement_id: str
    ) -> list[RequirementRecord]:
        """Every Requirement carrying this Requirement ID, bounded to two.

        Two rows are enough to tell "one" from "more than one"; a relation
        target that resolves ambiguously must be refused, never adopted.
        """

    def read_project(self, project_id: str) -> ProjectRecord | None:
        """Read the Project a Requirement belongs to."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Documents attached to this Requirement entity."""

    def resolve_document(self, document_id: str) -> DocumentNode | None:
        """Read one Document back by id."""

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        """Documents nested directly under this Document."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content."""

    def requirement_relations(self, entity_id: str) -> RequirementRelations:
        """The Depends On and Affects edges this Requirement already has."""

    def add_depends_on(self, entity_id: str, target_entity_id: str) -> None:
        """Add one Depends On edge. Fibery maintains the inverse Blocks."""

    def add_affects(self, entity_id: str, target_entity_id: str) -> None:
        """Add one Affects edge. Fibery maintains the inverse Impacted By."""

    def set_requirement_state(self, entity_id: str, state: str) -> None:
        """Move the Requirement's workflow State."""


class DispatchWorkspace(Protocol):
    """Operations the Requirement dispatcher performs against Fibery.

    Reads that revalidate a selected route and preflight the Standard
    candidates of a successful RAW result, and one write: the inherited
    candidate `Draft -> Process` State. It creates, deletes and relates
    nothing, and never touches a Document.
    """

    def read_requirement(self, entity_id: str) -> RequirementRecord | None:
        """Read one Requirement entity by id."""

    def find_requirements_by_requirement_id(
        self, requirement_id: str
    ) -> list[RequirementRecord]:
        """Every Requirement carrying this Requirement ID, bounded to two."""

    def derived_from(self, entity_id: str) -> list[RequirementRecord]:
        """The Requirements this one derives from, through Derived From."""

    def set_requirement_state(self, entity_id: str, state: str) -> None:
        """Move the Requirement's workflow State."""


class RunnerWorkspace(DispatchWorkspace, Protocol):
    """Operations the `sdlc worker run` runner performs against Fibery.

    The dispatcher's operations, plus the runner's own Processing Status
    operations: validate the Field, find the eligible work, write one status.
    `read_requirement` carries the status back, which is the read-back every
    status write is confirmed by. It creates, deletes and relates nothing,
    never touches a Document, and writes no Field but Processing Status and
    the dispatcher's inherited candidate State.
    """

    @property
    def lock_scope(self) -> str:
        """Stable identity of the workspace, for the runner's execution lock."""

    def validate_processing_status_field(self, options: Sequence[str]) -> None:
        """Raise FiberyError unless Processing Status is a single-select with
        exactly these option names."""

    def find_eligible_requirements(
        self, routes: Sequence[tuple[str, str]], status: str
    ) -> list[RequirementRecord]:
        """Requirements in every Project whose `(Type, State)` is one of
        `routes` and whose Processing Status is `status`, in
        `fibery/public-id` ascending order, bounded to one page."""

    def set_processing_status(self, entity_id: str, status: str) -> None:
        """Set the Processing Status single-select by option name."""
