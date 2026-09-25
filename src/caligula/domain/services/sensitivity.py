"""Sensitivity analysis: what does the conclusion depend on?

Each independent origin is removed in turn and the verdict recomputed. If
the verdict, a sub-claim's status or the leading hypothesis changes, the
conclusion depends on that origin. This tells the editor what to verify
twice before publishing, and the accused what they would need to answer.
A conclusion that survives the loss of any single origin is robust; one
that rests on a single document is not, however strong that document looks.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from caligula.domain.model.verdict import Dependency, Verdict


def _snapshot(v: Verdict) -> dict[str, str]:
    snap = {"verdict": v.verdict}
    snap |= {c.id: c.status for c in v.by_subclaim}
    snap |= {f"leading {'/'.join(m.hypotheses)}": (m.ranking or ["none"])[0] for m in v.ach}
    return snap


def dependencies(
    baseline: Verdict,
    origins: Iterable[tuple[str, list[str]]],
    evaluate_without: Callable[[str], Verdict],
) -> list[Dependency]:
    """`origins`: (cluster id, members) pairs; `evaluate_without(cluster)` recomputes the verdict without it."""
    before = _snapshot(baseline)
    out = []
    for cluster, members in origins:
        after = _snapshot(evaluate_without(cluster))
        changes = [f"{key} {before[key]} -> {after.get(key, 'gone')}"
                   for key in before if after.get(key) != before[key]]
        if changes:
            out.append(Dependency(origin=sorted(members), changes=changes,
                                  changes_verdict=after["verdict"] != before["verdict"]))
    return sorted(out, key=lambda d: (not d.changes_verdict, -len(d.changes), d.origin))
