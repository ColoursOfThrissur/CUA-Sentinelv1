import os

path = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    "..", "backend", "core", "blender_pipeline",
    "progressive_v2", "test_transforms.py"
))

OLD = '''    def test_stomp_breaks_cache_coherence_on_parent_move(self):
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
        )'''

NEW = '''    def test_stomp_world_matrix_not_produced_by_compute_world(self):
        """The stomp assigns world_matrix directly, bypassing compute_world.
        This means the stored world_matrix object was never produced by the
        cache mechanism — it has no parent context.

        Verify: after a stomp, calling compute_world with the SAME parent
        returns the stomped object as a cache hit (is_world_valid is True),
        even though the matrix was not produced by compute_world.  This is
        the architectural hazard: the cache trusts a matrix it didn't compute.

        The correct fix (executor never writes world_matrix) prevents this
        entirely — the sentinel test above catches any regression.
        """
        root, parent, child = self._make_chain()

        # Stomp: replace world_matrix with a new object (same content)
        stomped_wm = WorldMatrix.from_local(LocalTransform(
            position=list(child.world_matrix.position),
            rotation=list(child.world_matrix.rotation),
        ))
        child.world_matrix = stomped_wm

        # parent_revision on child state is unchanged by the stomp
        assert child.parent_revision == parent.revision, (
            "Stomp must not change parent_revision on the state"
        )

        # is_world_valid returns True — cache appears valid
        assert child.is_world_valid(parent.revision), (
            "Cache appears valid after stomp (architectural hazard)"
        )

        # compute_world returns the stomped object without recomputing
        returned = child.compute_world(parent.world_matrix, parent.revision)
        assert returned is stomped_wm, (
            "compute_world returned the stomped matrix as a cache hit — "
            "the matrix was not produced by compute_world"
        )

        # The only reliable guard is the write-detection sentinel (above).
        # Numerical comparison cannot distinguish stomped from correct matrix.'''

content = open(path, encoding="utf-8").read()
assert OLD in content, "OLD block not found in file"
content = content.replace(OLD, NEW, 1)
with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("done,", content.count("\n"), "lines")
