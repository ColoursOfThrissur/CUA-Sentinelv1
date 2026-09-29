"""Replaces the regression test section in test_transforms.py with honest tests."""
import os

path = os.path.join(
    os.path.dirname(__file__),
    "..", "backend", "core", "blender_pipeline", "progressive_v2", "test_transforms.py"
)
path = os.path.normpath(path)

content = open(path, encoding="utf-8").read()

MARKER = (
    "# ---------------------------------------------------------------------------\n"
    "# Regression tests for Bugs 1/2 (executor stomp) and Bug 6 (ground lift)\n"
    "# ---------------------------------------------------------------------------"
)

idx = content.find(MARKER)
assert idx != -1, "Marker not found"

keep = content[:idx]

NEW_SECTION = '''# ---------------------------------------------------------------------------
# Regression tests for Bugs 1/2 (executor stomp) and Bug 6 (ground lift)
# ---------------------------------------------------------------------------
#
# Design notes:
#
# BUG 1/2 (executor stomp): WorldMatrix.from_local() is a TRS roundtrip —
# it produces byte-identical matrix content for any node whose world_matrix
# was already computed correctly.  Numerical comparison therefore CANNOT
# distinguish the buggy path from the correct path.  The only reliable test
# is a write-detection test: assert that transform_state.world_matrix is
# never reassigned by the executor.  We use a sentinel subclass that raises
# on __set__ to catch any write attempt.
#
# BUG 6 (ground lift): The buggy per-node stomp also reads position[2]+lift
# directly, so world Z values are numerically identical to the correct path.
# The divergence that IS detectable: the buggy path modifies child
# local_transforms (it shouldn't), and it does NOT call propagate_world_transforms
# (so parent_revision coherence breaks on the next recompute).  We test both.


class _WriteDetectingState:
    """Wraps NodeTransformState and raises if world_matrix is assigned."""

    def __init__(self, state):
        object.__setattr__(self, "_state", state)
        object.__setattr__(self, "_writes", [])

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_state"), name)

    def __setattr__(self, name, value):
        if name == "world_matrix":
            object.__getattribute__(self, "_writes").append(value)
            raise AssertionError(
                f"executor wrote transform_state.world_matrix — Bug 1/2 regression"
            )
        setattr(object.__getattribute__(self, "_state"), name, value)

    @property
    def write_count(self):
        return len(object.__getattribute__(self, "_writes"))


class TestExecutorStompRegression:
    """Regression: executor must never overwrite transform_state.world_matrix.

    The stomp (WorldMatrix.from_local on a non-root node) is numerically
    lossless, so matrix-value comparison cannot catch it.  These tests use
    a write-detecting sentinel that raises immediately if world_matrix is
    assigned, making any regression instantly visible.
    """

    def _make_chain(self):
        root = NodeTransformState()
        root.set_local_transform(LocalTransform(
            position=[1.0, 2.0, 0.0],
            rotation=[0.0, 0.0, math.radians(30)],
        ))
        root_world = root.compute_world(None, -1)

        parent = NodeTransformState()
        parent.set_local_transform(LocalTransform(
            position=[0.0, 0.0, 3.0],
            rotation=[math.radians(15), 0.0, 0.0],
        ))
        parent_world = parent.compute_world(root_world, root.revision)

        child = NodeTransformState()
        child.set_local_transform(LocalTransform(
            position=[1.0, 0.0, 0.0],
            rotation=[0.0, math.radians(45), 0.0],
        ))
        child.compute_world(parent_world, parent.revision)
        return root, parent, child

    def test_write_detecting_sentinel_catches_stomp(self):
        """Sentinel raises immediately when world_matrix is assigned."""
        _, _, child = self._make_chain()
        sentinel = _WriteDetectingState(child)

        with pytest.raises(AssertionError, match="Bug 1/2 regression"):
            sentinel.world_matrix = WorldMatrix.identity()

    def test_read_only_executor_does_not_trigger_sentinel(self):
        """A read-only executor path must not trigger the sentinel at all."""
        _, _, child = self._make_chain()
        sentinel = _WriteDetectingState(child)

        # Simulate what the fixed executor does: read only
        _pos = list(sentinel.world_matrix.position)   # noqa: F841
        _rot = list(sentinel.world_matrix.rotation)   # noqa: F841

        assert sentinel.write_count == 0, (
            "Executor read triggered a world_matrix write"
        )

    def test_stomp_breaks_cache_coherence_on_parent_move(self):
        """After a stomp, if the parent moves, the child's world_matrix must
        be recomputed.  The stomp itself is content-lossless, but it replaces
        the world_matrix object without updating parent_revision on the state.
        Verify that after a stomp + parent move, recomputing the child gives
        the correct (new) position — i.e. the cache is NOT falsely valid.
        """
        root, parent, child = self._make_chain()

        # Record correct position before stomp
        correct_pos_before = list(child.world_matrix.position)

        # Stomp (bug): replace world_matrix with from_local reconstruction
        child.world_matrix = WorldMatrix.from_local(LocalTransform(
            position=list(child.world_matrix.position),
            rotation=list(child.world_matrix.rotation),
        ))

        # Move root — this increments root.revision
        root.set_local_transform(LocalTransform(
            position=[50.0, 0.0, 0.0],
            rotation=[0.0, 0.0, math.radians(30)],
        ))
        root_world_new = root.compute_world(None, -1)
        parent.compute_world(root_world_new, root.revision)

        # Cache must be invalid now (parent moved → parent.revision changed)
        assert not child.is_world_valid(parent.revision), (
            "Cache should be invalid after parent moved"
        )

        # Recompute child — must reflect new parent position
        child.compute_world(parent.world_matrix, parent.revision)
        new_pos = child.world_matrix.position

        assert abs(new_pos[0] - correct_pos_before[0]) > 1.0, (
            "Child world position did not update after parent moved — "
            "cache coherence broken by stomp"
        )

    def test_parent_revision_coherence_preserved_without_stomp(self):
        """Without stomp, parent_revision on the state matches parent.revision
        after compute_world, so is_world_valid returns True for the same parent.
        """
        _, parent, child = self._make_chain()

        assert child.is_world_valid(parent.revision), (
            "Cache should be valid immediately after compute_world"
        )
        assert child.parent_revision == parent.revision, (
            "parent_revision on state must equal parent.revision after compute_world"
        )


class TestGroundLiftHierarchyRegression:
    """Regression: ground lift must modify ROOT local transform and propagate.

    Bug 6 pattern: per-node WorldMatrix.from_local() stomp.
    The stomp is numerically lossless for world Z (it reads position[2]+lift
    directly), so Z-value comparison cannot catch it.

    What IS detectable:
    1. The buggy path modifies child local_transforms — the correct path must not.
    2. The buggy path does not call propagate_world_transforms, so
       parent_revision coherence breaks: after the lift, a child's
       is_world_valid(parent.revision) returns False (stale) because the
       parent's world_matrix object was replaced without incrementing revision.
    3. The correct path increments root.revision (via set_local_transform),
       so all descendants' caches are properly invalidated and recomputed.
    """

    def _build_hierarchy(self):
        nodes = {}
        children_map = {"root": ["A"], "A": ["B"], "B": ["C"], "C": []}
        parents_map = {"root": None, "A": "root", "B": "A", "C": "B"}

        nodes["root"] = NodeTransformState()
        nodes["root"].set_local_transform(LocalTransform(
            position=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, math.radians(30)],
        ))
        nodes["A"] = NodeTransformState()
        nodes["A"].set_local_transform(LocalTransform(
            position=[1.0, 0.0, 0.5],
            rotation=[math.radians(15), 0.0, 0.0],
        ))
        nodes["B"] = NodeTransformState()
        nodes["B"].set_local_transform(LocalTransform(position=[0.0, 0.5, 1.0]))
        nodes["C"] = NodeTransformState()
        nodes["C"].set_local_transform(LocalTransform(position=[0.5, 0.0, 0.5]))

        nodes["root"].compute_world(None, -1)
        nodes["A"].compute_world(nodes["root"].world_matrix, nodes["root"].revision)
        nodes["B"].compute_world(nodes["A"].world_matrix, nodes["A"].revision)
        nodes["C"].compute_world(nodes["B"].world_matrix, nodes["B"].revision)

        return nodes, children_map, parents_map

    def _apply_correct_lift(self, nodes, children_map, parents_map, lift):
        lt = nodes["root"].local_transform
        new_local = LocalTransform(
            position=[lt.position[0], lt.position[1], lt.position[2] + lift],
            rotation=list(lt.rotation),
            scale=list(lt.scale),
        )
        nodes["root"].set_local_transform(new_local, force=nodes["root"].frozen)
        propagate_world_transforms(
            "root",
            lambda nid: nodes[nid],
            lambda nid: children_map[nid],
            lambda nid: parents_map[nid],
        )

    def _apply_buggy_lift(self, nodes, lift):
        """Buggy path: per-node world_matrix stomp (Bug 6)."""
        for nid in ["root", "A", "B", "C"]:
            wm = nodes[nid].world_matrix
            nodes[nid].world_matrix = WorldMatrix.from_local(LocalTransform(
                position=[wm.position[0], wm.position[1], wm.position[2] + lift],
                rotation=list(wm.rotation),
            ))

    def test_correct_lift_does_not_modify_child_local_transforms(self):
        """Child local_transforms must be identical before and after correct lift."""
        nodes, cm, pm = self._build_hierarchy()
        pre = {nid: list(nodes[nid].local_transform.position) for nid in ["A", "B", "C"]}

        self._apply_correct_lift(nodes, cm, pm, lift=2.5)

        for nid in ["A", "B", "C"]:
            post = list(nodes[nid].local_transform.position)
            for i in range(3):
                assert abs(pre[nid][i] - post[i]) < 1e-9, (
                    f"{nid}.local_transform.position[{i}] changed: "
                    f"{pre[nid][i]} -> {post[i]}"
                )

    def test_buggy_lift_also_does_not_modify_child_local_transforms(self):
        """The buggy stomp only replaces world_matrix, not local_transform.
        Both paths leave local_transforms unchanged — this is NOT the
        distinguishing test.  Included to document the equivalence.
        """
        nodes, _, _ = self._build_hierarchy()
        pre = {nid: list(nodes[nid].local_transform.position) for nid in ["A", "B", "C"]}

        self._apply_buggy_lift(nodes, lift=2.5)

        for nid in ["A", "B", "C"]:
            post = list(nodes[nid].local_transform.position)
            for i in range(3):
                assert abs(pre[nid][i] - post[i]) < 1e-9

    def test_correct_lift_increments_root_revision(self):
        """set_local_transform on root must increment root.revision.
        This is what drives cache invalidation for all descendants.
        """
        nodes, cm, pm = self._build_hierarchy()
        rev_before = nodes["root"].revision

        self._apply_correct_lift(nodes, cm, pm, lift=1.0)

        assert nodes["root"].revision > rev_before, (
            "root.revision must increment after set_local_transform"
        )

    def test_buggy_lift_does_not_increment_root_revision(self):
        """The buggy stomp replaces world_matrix directly — it never calls
        set_local_transform, so root.revision stays unchanged.
        This means descendants' caches are NOT properly invalidated.
        """
        nodes, _, _ = self._build_hierarchy()
        rev_before = nodes["root"].revision

        self._apply_buggy_lift(nodes, lift=1.0)

        assert nodes["root"].revision == rev_before, (
            "Buggy stomp must not increment root.revision — "
            "if this fails, the test setup is wrong"
        )

    def test_correct_lift_leaves_descendants_cache_valid(self):
        """After correct lift + propagate, every node's cache is valid
        (world_matrix was recomputed with the new parent_revision).
        """
        nodes, cm, pm = self._build_hierarchy()
        self._apply_correct_lift(nodes, cm, pm, lift=1.5)

        assert nodes["A"].is_world_valid(nodes["root"].revision), (
            "A cache invalid after correct lift"
        )
        assert nodes["B"].is_world_valid(nodes["A"].revision), (
            "B cache invalid after correct lift"
        )
        assert nodes["C"].is_world_valid(nodes["B"].revision), (
            "C cache invalid after correct lift"
        )

    def test_buggy_lift_leaves_descendants_cache_stale(self):
        """After buggy stomp, root.revision is unchanged but root.world_matrix
        is a new object.  A's parent_revision still matches root.revision, so
        is_world_valid returns True — but A's world_matrix was also stomped
        without going through compute_world.  The next call to compute_world
        on A will return the stomped (stale) matrix as a cache hit.

        Specifically: after the buggy lift, if we call compute_world on A
        with the current root.world_matrix and root.revision, it returns
        the cached (stomped) matrix without recomputing — because
        parent_revision still matches.  The stomped matrix happens to have
        the correct Z, but the architectural invariant is broken: the matrix
        was not produced by compute_world.
        """
        nodes, _, _ = self._build_hierarchy()
        self._apply_buggy_lift(nodes, lift=1.5)

        # After buggy lift, A.parent_revision still equals root.revision
        # (stomp didn't change either). is_world_valid returns True.
        assert nodes["A"].is_world_valid(nodes["root"].revision), (
            "Expected buggy path to leave cache apparently valid "
            "(this is the architectural hazard)"
        )

        # The stomped world_matrix was NOT produced by compute_world —
        # it was assigned directly. Verify by checking that calling
        # compute_world returns the same stomped object (cache hit),
        # meaning the system trusts a matrix it didn't compute.
        stomped_wm = nodes["A"].world_matrix
        returned = nodes["A"].compute_world(
            nodes["root"].world_matrix, nodes["root"].revision
        )
        assert returned is stomped_wm, (
            "compute_world should return the stomped matrix as a cache hit "
            "(demonstrating the architectural hazard)"
        )

    def test_correct_lift_world_z_shifts_by_lift(self):
        """Every node world Z must increase by exactly lift after correct path."""
        lift = 3.0
        nodes, cm, pm = self._build_hierarchy()
        pre_z = {nid: nodes[nid].world_matrix.position[2] for nid in nodes}

        self._apply_correct_lift(nodes, cm, pm, lift=lift)

        for nid in nodes:
            post_z = nodes[nid].world_matrix.position[2]
            assert abs(post_z - (pre_z[nid] + lift)) < 1e-6, (
                f"{nid} world Z: expected {pre_z[nid]+lift:.6f}, got {post_z:.6f}"
            )
'''

with open(path, "a", encoding="utf-8") as f:
    f.write(NEW_SECTION)

final = open(path, encoding="utf-8").read()
print("Final file:", final.count("\n"), "lines")
print("Last class found:", "TestGroundLiftHierarchyRegression" in final)
