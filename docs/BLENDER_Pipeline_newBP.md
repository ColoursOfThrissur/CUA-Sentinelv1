# Blender Assembly Pipeline — Architecture Blueprint v5

**Status:** ARCHITECTURE PROPOSED — replaces v4 execution model
**Audience:** An implementing coding assistant with no memory of prior discussion
**Purpose:** Define a progressive, hierarchical, failure-recoverable Blender assembly pipeline for complex models.

---

# 0. Core Philosophy

The pipeline must behave like a **smart jigsaw-puzzle solver**.

It must NOT attempt to generate an entire complex model in one pass.

Instead:

> **Understand the whole model → recursively decompose only where useful → build the smallest independently reliable units → verify and lock them → progressively merge verified units upward → repeat until the root model is complete.**

The system must maintain persistent execution state throughout the build.

The LLM provides semantic/creative decisions.

Code owns:

* hierarchy integrity
* dependency resolution
* numeric geometry
* transforms
* socket calculations
* build scheduling
* state transitions
* cleanup
* retries
* verification gates
* rollback
* assembly merging

The existing numeric-geometry invariant from v4 remains mandatory.

---

# 1. Core Invariant

> **No numeric offset or rotation value that reaches Blender may come directly from the LLM.**

Every axis of every transform is either:

1. computed deterministically from known geometry, or
2. derived from a closed-vocabulary semantic hint selected by the LLM.

There is no path where:

```text
LLM raw number
    ↓
Blender transform
```

is allowed.

This invariant applies recursively to every assembly and every build level.

---

# 2. New Architectural Model

The previous architecture treated the complete model as a flat part graph.

v5 introduces three distinct structural concepts.

## 2.1 Containment Hierarchy

Defines:

> What belongs inside what?

```text
MODEL
└── ASSEMBLY
    ├── ASSEMBLY
    │   ├── PART
    │   └── PART
    ├── PART
    └── ASSEMBLY
        └── PART
```

Example:

```text
pirate_ship
├── hull_assembly
│   ├── hull_body
│   └── keel
├── deck_assembly
│   ├── main_deck
│   └── railing_assembly
│       ├── railing_post
│       └── railing_bar
├── mast_assembly
│   ├── mast_pole
│   └── sail_assembly
│       ├── sail
│       └── boom
└── armament_assembly
    └── cannon_assembly
        ├── barrel
        ├── base
        └── wheels
```

---

## 2.2 Dependency DAG

Defines:

> What must be available before this node can be built, merged, or verified?

Example:

```text
wheel_definition
       ↓
cannon_assembly
       ↓
armament_assembly
       ↓
ship
```

The dependency graph must be cycle-free.

Build order is determined from the dependency graph, not from arbitrary numeric depth.

---

## 2.3 Relationship Graph

Defines relationships that cross containment boundaries.

Example:

```text
mast.rigging_anchor
          │
          │ rope connection
          ▼
railing.rigging_anchor
```

A connection does not require the rope or connector to belong simultaneously to both assemblies.

Relationship records reference sockets/interfaces.

---

# 3. Hierarchy Levels

Every generated object belongs to one of these conceptual levels:

```text
MODEL
  ↓
ASSEMBLY
  ↓
SUB-ASSEMBLY
  ↓
PART
```

There is no requirement that every branch reaches the same depth.

Example:

```text
ROBOT
├── body_assembly
│   ├── torso          ← leaf
│   └── chest_panel    ← leaf
│
├── arm_assembly
│   ├── upper_arm      ← leaf
│   └── hand_assembly
│       ├── palm       ← leaf
│       └── finger     ← leaf
```

The hierarchy is therefore **variable-depth**.

---

# 4. Progressive Decomposition

## 4.1 Principle

The system recursively decomposes a node only when further decomposition provides meaningful benefits.

It must NOT blindly decompose until a fixed depth.

For each node:

```text
Node
 ↓
Can this node be reliably built and verified as one unit?
 ├── YES → LEAF
 └── NO  → DECOMPOSE
```

---

# 4.2 Decomposition Stop Conditions

A node may become a leaf when all or most of the following are satisfied:

### A. Geometric manageability

The geometry can be generated reliably within the current pipeline capabilities.

### B. Semantic cohesion

The components represent one meaningful object.

### C. Independent verification

The node can be verified without requiring the complete parent model.

### D. Clear interface

The node exposes sufficient sockets/mount points for its parent.

### E. Further decomposition has low value

Splitting the node further would not materially improve:

* generation reliability
* verification
* repairability
* reuse
* scheduling

### F. Complexity budget is satisfied

The node is below configured limits.

---

# 4.3 Hard Safety Limits

The system must still enforce:

```text
MAX_HIERARCHY_DEPTH
MAX_CHILDREN_PER_NODE
MAX_PARTS_PER_ASSEMBLY
MAX_TOTAL_NODES
MAX_DECOMPOSITION_ATTEMPTS
```

These are safety limits, NOT the primary decomposition strategy.

---

# 5. Recursive Decomposition Algorithm

Conceptually:

```text
decompose(node):

    evaluate node complexity

    if node is buildable:
        mark node LEAF
        return

    if safety limits exceeded:
        mark node LEAF_WITH_WARNING
        return

    request semantic decomposition

    validate proposed children

    recursively evaluate each child

    return hierarchy
```

The LLM proposes semantic structure.

Code validates the structure.

The LLM must not control hierarchy integrity.

---

# 6. Persistent Model Manifest

The entire build must have a persistent temporary execution manifest.

This is the pipeline's working state.

Conceptually:

```text
build_manifest.json
```

contains:

```text
MODEL
├── model_id
├── description
├── version
└── root_node

HIERARCHY
├── nodes
├── parent relationships
└── instances

DEPENDENCIES
├── dependency edges
└── build ordering information

RELATIONSHIPS
├── socket connections
└── cross-assembly references

BUILD_STATE
├── current_node
├── queue
├── frontier
├── completed
├── failed
├── skipped
└── active

VERIFICATION
├── results
├── failures
└── affected nodes

RETRY
├── attempt count
├── failure reason
└── retry stage

CHECKPOINTS
└── last committed state
```

The exact schema is implementation-defined.

The architectural requirement is that the state must be sufficient to resume the build after interruption.

---

# 7. Temporary vs Permanent State

The execution manifest is temporary.

During successful completion:

```text
temporary build state
        ↓
final model committed
        ↓
temporary execution state deleted
```

Permanent model information must remain in the final model/manifest as appropriate.

Do NOT delete the actual model hierarchy merely because the temporary build manifest is removed.

---

# 8. Node State Machine

Every node must have an explicit state.

Minimum states:

```text
PLANNED
DECOMPOSING
READY
BUILDING
VERIFYING
VERIFIED
MERGING
FAILED
RETRYING
SKIPPED
STALE
```

Example:

```text
PLANNED
   ↓
READY
   ↓
BUILDING
   ↓
VERIFYING
   ↓
VERIFIED
```

Failure:

```text
VERIFYING
   ↓
FAILED
   ↓
CLEANUP
   ↓
RETRYING
```

After retry limit:

```text
FAILED
   ↓
SKIPPED
```

---

# 9. Build Frontier

The system must maintain a **build frontier**.

The frontier contains nodes that are currently actionable.

A node enters the frontier only when:

```text
node is READY
AND
required dependencies are VERIFIED
AND
parent context is valid
AND
required sockets/interfaces exist
```

The system must never blindly iterate through the original node list.

---

# 10. Smart Scheduler

The scheduler chooses the next buildable node.

It should consider:

```text
dependency readiness
parent readiness
structural importance
whether it blocks other nodes
confidence
estimated complexity
previous failures
whether it creates useful assembly progress
```

The scheduler may prioritize foundational pieces or independent branches.

Example:

```text
Hull
Deck
Cannon
Mast
Railing
Sail
Armament
Ship
```

The exact order is determined by the dependency graph and current state.

---

# 11. Bottom-Up Progressive Assembly

The system builds from reliable smaller units toward larger assemblies.

Example:

```text
wheel
barrel
base
   ↓
CANNON
   ↓
CANNON ASSEMBLY VERIFIED
```

Then:

```text
Cannon
Cannon
Cannon
Cannon
   ↓
ARMAMENT ASSEMBLY
```

Then:

```text
Hull
Deck
Armament
Mast
   ↓
SHIP
```

Each merge is itself a build/verification boundary.

---

# 12. Assembly Merge Operation

A merge is a first-class operation.

```text
BUILD
 ↓
VERIFY
 ↓
LOCK
 ↓
MERGE
 ↓
VERIFY
 ↓
LOCK
```

Example:

```text
wheel ✓
barrel ✓
base ✓
      ↓
    MERGE
      ↓
cannon
      ↓
   VERIFY
      ↓
    LOCK
```

The parent must never consume an unverified child as a trusted assembly.

---

# 13. Assembly Contract

Every assembly exposes an interface.

Conceptually:

```text
AssemblyContract
├── identity
├── local coordinate system
├── children
├── dependencies
├── bounding information
├── sockets
├── constraints
├── expected geometry
├── verification rules
└── output interface
```

Example:

```text
CannonAssembly

Internal:
    barrel
    base
    wheel_left
    wheel_right

Public sockets:
    base_bottom
    barrel_forward

Verification:
    wheels exist
    barrel exists
    wheels contact carriage
    barrel aligns with carriage
```

Parent assemblies must interact through the public interface.

They must not depend on arbitrary internal geometry.

---

# 14. Instance Definitions

Repeated assemblies must distinguish:

```text
DEFINITION
```

from:

```text
INSTANCE
```

Example:

```text
cannon_definition
    │
    ├── cannon_instance_01
    ├── cannon_instance_02
    ├── cannon_instance_03
    └── cannon_instance_04
```

The definition is built and verified once where possible.

Instances provide placements.

The architecture must support this even if the initial Blender implementation uses copied geometry rather than linked Blender instances.

---

# 15. Failure Handling

Failure must be surgical.

Never automatically destroy the entire model because one child failed.

---

## 15.1 Local Failure

Example:

```text
CANNON
├── barrel ✓
├── base ✓
├── wheel_left ✓
└── wheel_right ✗
```

Action:

```text
remove wheel_right
 ↓
retry wheel_right
 ↓
verify cannon
```

---

## 15.2 Assembly Failure

If local repair cannot resolve the problem:

```text
remove cannon assembly
 ↓
rebuild cannon assembly
 ↓
verify
```

Only the affected assembly is regenerated.

---

## 15.3 Repeated Failure

After configured retry limits:

```text
FAILED
 ↓
SKIPPED
```

The parent must be informed.

---

# 16. Required vs Optional Components

Each node should carry a semantic importance classification.

Conceptually:

```text
REQUIRED
OPTIONAL
DECORATIVE
```

If an optional node fails:

```text
node = SKIPPED
parent = DEGRADED
build may continue
```

If a required node fails:

```text
node = SKIPPED
parent = BLOCKED
```

The root cannot report full success while required components are missing.

---

# 17. Degraded Completion

The final result must distinguish:

```text
SUCCESS
```

from:

```text
SUCCESS_WITH_OPTIONAL_COMPONENTS_SKIPPED
```

and:

```text
FAILED
```

Example:

```text
Expected cannons: 4
Built cannons: 3
Skipped: 1

Final status:
COMPLETED_DEGRADED
```

The system must never silently hide missing components.

---

# 18. Cleanup Before Retry

A failed node must not leave faulty geometry in the scene.

Retry flow:

```text
FAIL
 ↓
identify generation objects belonging to failed node
 ↓
delete faulty generation objects
 ↓
purge only owned temporary/orphan resources
 ↓
restore last valid checkpoint
 ↓
retry
```

Existing user scene objects must remain untouched.

---

# 19. Checkpointing

After every successful meaningful boundary:

```text
verified leaf
verified sub-assembly
verified assembly
successful merge
```

the manifest should be checkpointed.

Example:

```text
Checkpoint 1:
Hull ✓

Checkpoint 2:
Hull ✓
Deck ✓

Checkpoint 3:
Hull ✓
Deck ✓
Cannon ✓

Checkpoint 4:
Armament ✓
```

If the process crashes:

```text
load latest checkpoint
 ↓
restore state
 ↓
continue from frontier
```

Previously verified geometry must not be unnecessarily regenerated.

---

# 20. Dirty Propagation

If a previously verified component changes:

```text
Cannon changed
```

dependent nodes become:

```text
Cannon       DIRTY
Armament     STALE
Deck         STALE
Ship         STALE
```

Unrelated branches remain:

```text
Hull         CLEAN
Mast         CLEAN
Sail         CLEAN
```

Only affected nodes need reconsideration.

---

# 21. Progressive Verification

Verification occurs at every level.

## Part level

```text
geometry validity
dimensions
local bounds
```

## Assembly level

```text
child placement
socket alignment
intersections
expected topology
```

## Parent level

```text
assembly placement
assembly interfaces
cross-assembly relationships
```

## Root level

```text
overall structure
required components
global spatial validity
final dimensions
```

Verification therefore becomes:

```text
PART
 ↓
SUB-ASSEMBLY
 ↓
ASSEMBLY
 ↓
MODEL
```

---

# 22. Existing Stage 0 Remains

## Stage 0 — Object Understanding

Input:

```text
Raw user prompt
```

Output:

```text
category
rests_on_surface
style_tag
scale_anchor_m
```

This remains an LLM semantic stage.

No change to the numeric-transform invariant.

---

# 23. Stage 1 Becomes Node Topology

The old Stage 1 generated a complete flat part topology.

v5 changes this.

Stage 1 operates on **one hierarchy node at a time**.

Input:

```text
current node
parent context
model context
```

Output:

```text
children[]
```

Children may be:

```text
PART
ASSEMBLY
INSTANCE
RELATIONSHIP
```

No raw transforms.

No raw offsets.

---

# 24. Stage 2 Becomes Node Dimensions

Stage 2 operates only on the current build node.

It produces dimensions for its immediate geometry.

The existing dimension validation remains.

Dimensions are validated against:

```text
scale_anchor
parent dimensions
child proportions
known primitive constraints
```

Severe inconsistencies are rejected.

---

# 25. Stage 3 Becomes Node Attachment Semantics

Stage 3 operates on the current node.

It provides closed-vocabulary semantic information:

```text
socket_type
height_hint
pierce_direction
connects_to
cut_face
radial_count
radial_index
array_count
array_index
```

It must never provide raw transform offsets.

---

# 26. Stage 4 Remains Deterministic Resolution

Stage 4 resolves transforms for the current node.

It remains pure code.

```text
Stage 3 semantic hints
+
real geometry
+
parent/child interfaces
        ↓
Stage 4
        ↓
ResolvedTransform
```

All existing socket resolver rules remain unless explicitly superseded by the hierarchical assembly system.

---

# 27. Stage 4.5 Modifier Intent

Modifier intent continues to operate on the current node.

Modifiers are applied only after geometry/boolean operations according to existing v4 rules.

---

# 28. Stage 5 Blender Execution

Stage 5 now executes a **single build transaction for the current node/assembly**.

Each node receives its own generation scope.

Example:

```text
sentinel_gen_<task>_<node>_<attempt>
```

This allows surgical deletion.

No:

```text
clear_scene
```

is permitted.

Existing user scene geometry remains untouched.

---

# 29. Stage 6 Verification

Stage 6 verifies the current node.

Existing verification mechanisms remain:

1. spatial/interpenetration
2. local mesh dimensions
3. connector reach
4. boolean postconditions

Additional hierarchical checks are added:

5. child completeness
6. socket/interface validity
7. dependency validity
8. expected instance count
9. assembly bounds
10. parent attachment validity

Verification must fail closed.

```text
verification exception
        ↓
FAIL
```

Never:

```text
exception
 ↓
warning
 ↓
SUCCESS
```

---

# 30. Retry Routing

Failure determines the retry point.

Example:

```text
Dimension failure
    → Stage 2

Semantic attachment failure
    → Stage 3

Socket/transform failure
    → Stage 3/4

Geometry generation failure
    → Stage 5

Modifier failure
    → Stage 4.5

Verification failure
    → appropriate preceding stage

Non-retryable mesh corruption
    → rebuild node from clean checkpoint
```

Retry occurs only for the affected node whenever possible.

---

# 31. Main Progressive Assembly Controller

The high-level execution model becomes:

```text
Stage 0
  ↓
Create Model Manifest
  ↓
Recursive Hierarchical Decomposition
  ↓
Validate Hierarchy
  ↓
Build Dependency DAG
  ↓
Create Initial Build Frontier
  ↓
┌─────────────────────────────────────┐
│         PROGRESSIVE LOOP             │
│                                     │
│  Pick best READY node               │
│          ↓                          │
│  Decompose if necessary             │
│          ↓                          │
│  Build node                         │
│          ↓                          │
│  Verify node                        │
│       /       \                     │
│     PASS      FAIL                  │
│      ↓          ↓                   │
│    LOCK      CLEANUP                │
│      │          ↓                   │
│      │       RETRY / SKIP           │
│      │          │                   │
│      └────┬─────┘                   │
│           ↓                         │
│    Update Manifest                  │
│           ↓                         │
│    Checkpoint                       │
│           ↓                         │
│    Can children merge?              │
│       /          \                  │
│     YES           NO                │
│      ↓             ↓               │
│   MERGE          NEXT NODE          │
│      ↓                              │
│   VERIFY                            │
│      ↓                              │
│   MOVE UP HIERARCHY                 │
│                                     │
│  Repeat until root resolved         │
└─────────────────────────────────────┘
  ↓
Final Model Verification
  ↓
Commit
  ↓
Delete temporary build manifest
```

---

# 32. Important: Do Not Pre-build Every Leaf

The recursive hierarchy may be known ahead of time, but the execution process must remain scheduler-driven.

Do NOT require:

```text
build every leaf
    ↓
only then assemble
```

Instead:

```text
build useful verified node
    ↓
if parent can now progress
    ↓
merge
    ↓
continue
```

The scheduler should continuously reassess the build frontier.

---

# 33. Jigsaw Principle

The system should optimize for:

> **Maximum verified structural progress per build action.**

It should prefer pieces that:

* unlock dependent nodes
* establish important foundations
* provide reusable definitions
* validate critical interfaces
* reduce uncertainty
* enable parent assembly
* are independently verifiable

It should avoid spending excessive effort on low-value decorative details while major structural assemblies remain unresolved.

---

# 34. Tree Depth vs Dependency Depth

Do not use one `depth` value for all purposes.

Maintain:

```text
hierarchy_depth
dependency_depth
```

Hierarchy:

```text
SHIP             0
 └── DECK        1
      └── RAILING 2
```

Dependency:

```text
CANNON → ARMAMENT → DECK → SHIP
```

The two systems answer different questions.

---

# 35. Cross-Assembly Connections

Connections must use interfaces.

Example:

```text
MAST
 └── rigging_anchor_A

RAILING
 └── rigging_anchor_B

RELATIONSHIP
 └── rope:
       source = mast.rigging_anchor_A
       target = railing.rigging_anchor_B
```

The connector's numeric geometry is computed deterministically from the resolved anchor positions.

---

# 36. Manifest Lifecycle

The manifest follows:

```text
CREATE
 ↓
DECOMPOSE
 ↓
PLAN
 ↓
BUILD
 ↓
CHECKPOINT
 ↓
BUILD
 ↓
CHECKPOINT
 ↓
...
 ↓
ROOT VERIFIED
 ↓
FINAL COMMIT
 ↓
DELETE TEMPORARY EXECUTION STATE
```

The manifest must be recoverable at every important boundary.

---

# 37. Final Success Requirements

`SUCCESS` is allowed only when:

```text
root verified
AND
all required children verified
AND
all required dependencies resolved
AND
all required interfaces valid
AND
final spatial verification passed
AND
no unresolved mandatory failures exist
```

If optional elements were skipped:

```text
COMPLETED_DEGRADED
```

If required elements failed:

```text
FAILED
```

---

# 38. Existing Blender Conventions Remain

```text
1 Blender unit = 1 meter

Rotation order:
Euler XYZ

Internal rotation:
radians

Blender I/O:
degrees where required

Cylinder/cone:
local +Z = depth axis

Verification:
LOCAL mesh bounds

Existing socket resolver:
preserved and extended where necessary
```

---

# 39. Existing v4 Safety Guarantees Remain Mandatory

The following must NOT regress:

* no `clear_scene`
* generation-scoped collections
* generation-prefixed object names
* transactional execution
* targeted orphan cleanup
* rollback on failure
* boolean ordering
* local dimension verification
* connector verification
* fail-closed verification
* deterministic transform resolution
* no raw LLM transform numbers
* Euler rotation composition through matrices
* world-pose calculation through parent chains

---

# 40. Recommended New File Structure

The existing structure should evolve toward:

```text
backend/core/blender_pipeline/

├── orchestrator.py
│
├── hierarchy/
│   ├── decomposer.py
│   ├── hierarchy_validator.py
│   ├── scheduler.py
│   ├── dependency_graph.py
│   ├── frontier.py
│   └── merger.py
│
├── state/
│   ├── build_manifest.py
│   ├── node_state.py
│   ├── checkpoint.py
│   └── dirty_propagation.py
│
├── stages/
│   ├── stage0_understanding.py
│   ├── stage1_topology.py
│   ├── stage2_dimensions.py
│   ├── stage3_semantics.py
│   ├── stage4_resolver.py
│   └── stage45_modifiers.py
│
├── execution/
│   ├── executor.py
│   ├── transaction.py
│   └── cleanup.py
│
├── verification/
│   ├── assembly_verification.py
│   ├── node_verification.py
│   └── hierarchy_verification.py
│
├── assembly_spec.py
├── blender_ops.py
└── broadcast.py
```

Exact naming can differ, but responsibilities should remain separated.

---

# 41. New Primary Execution Abstraction

The pipeline should conceptually move from:

```text
run_staged_pipeline(prompt)
```

toward:

```text
run_progressive_assembly(prompt)
```

Internally:

```text
manifest
 ↓
scheduler
 ↓
node
 ↓
node pipeline
 ↓
verification
 ↓
manifest update
 ↓
scheduler
```

The existing Stage 0–6 logic should be reused inside this loop rather than duplicated.

---

# 42. Fundamental Architectural Rule

The most important new rule is:

> **A stage operates on a node; the progressive controller operates on the model.**

Stages answer:

```text
How should THIS node be built?
```

The controller answers:

```text
Which node should be built next?
Should it be decomposed?
Did it succeed?
Should it be retried?
Can it merge?
What became available?
What became stale?
Is the model complete?
```

This separation must be maintained.

---

# 43. Target Architecture

The final conceptual system is:

```text
                         USER
                           │
                           ▼
                  MODEL UNDERSTANDING
                           │
                           ▼
                RECURSIVE DECOMPOSER
                           │
                           ▼
              ┌────────────────────────┐
              │     MODEL MANIFEST     │
              │                        │
              │  Containment Tree      │
              │  Dependency DAG        │
              │  Relationships         │
              │  Instances             │
              │  Sockets               │
              │  Build State           │
              │  Verification State    │
              └───────────┬────────────┘
                          │
                          ▼
                    SMART SCHEDULER
                          │
                          ▼
                 BUILD FRONTIER
                          │
                          ▼
             ┌────────────────────────┐
             │   CURRENT NODE         │
             │                        │
             │  Topology              │
             │  Dimensions            │
             │  Semantics             │
             │  Resolver              │
             │  Modifiers             │
             │  Blender               │
             │  Verification          │
             └───────────┬────────────┘
                         │
                    PASS / FAIL
                    /         \
                 PASS         FAIL
                  │             │
                LOCK        CLEANUP
                  │             │
                  │        RETRY / SKIP
                  │             │
                  └──────┬──────┘
                         ▼
                  UPDATE MANIFEST
                         │
                         ▼
                    CHECKPOINT
                         │
                         ▼
                  CAN MERGE UP?
                    /        \
                  YES         NO
                   │           │
                 MERGE       NEXT NODE
                   │
                   ▼
                VERIFY
                   │
                   ▼
              MOVE UP TREE
                   │
                  ...
                   │
                   ▼
              ROOT VERIFIED
                   │
                   ▼
           FINAL MODEL VERIFICATION
                   │
                   ▼
                  COMMIT
                   │
                   ▼
          DELETE TEMPORARY STATE
```

---

# 44. Definition of Done

The v5 architecture is considered correctly implemented when the system can:

1. Accept a complex model request.
2. Create a hierarchical model plan.
3. Recursively decompose only where necessary.
4. Stop decomposition at different depths for different branches.
5. Persist the complete build state.
6. Determine a dependency-aware build frontier.
7. Build one independently meaningful node at a time.
8. Verify each node before trusting it.
9. Remove faulty geometry after failure.
10. Retry only the affected node whenever possible.
11. Skip failed optional components without corrupting the parent.
12. Block parents when required components fail.
13. Merge verified children into progressively larger assemblies.
14. Verify every merge.
15. Maintain instance definitions separately from placements.
16. Track cross-assembly socket relationships.
17. Checkpoint successful progress.
18. Resume after process interruption.
19. Propagate changes only to affected dependents.
20. Produce a final verified root model.
21. Delete temporary execution state after successful completion.
22. Preserve all v4 deterministic geometry and Blender safety guarantees.

---

# 45. Final Design Principle

The pipeline is no longer:

```text
PROMPT
 ↓
GENERATE EVERYTHING
 ↓
BLENDER
```

It is:

```text
PROMPT
 ↓
UNDERSTAND
 ↓
DECOMPOSE
 ↓
PLAN
 ↓
SELECT NEXT PIECE
 ↓
BUILD
 ↓
VERIFY
 ↓
LOCK
 ↓
MERGE
 ↓
VERIFY
 ↓
SELECT NEXT PIECE
 ↓
...
 ↓
COMPLETE MODEL
```

The model is solved progressively like a jigsaw puzzle.

The system should always know:

```text
WHAT IS ALREADY SOLVED
WHAT IS CURRENTLY BEING SOLVED
WHAT CAN BE SOLVED NEXT
WHAT FAILED
WHAT MUST BE RETRIED
WHAT CAN BE SKIPPED
WHAT CAN NOW BE MERGED
WHAT BECAME INVALID
WHAT REMAINS BEFORE THE ROOT IS COMPLETE
```

This state-driven progressive assembly model is the foundation for complex-model reliability.
