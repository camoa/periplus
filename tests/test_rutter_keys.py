"""The keys that name things by path, declare sections, reshape values and mark a missed end."""

from __future__ import annotations

from periplus.engine.packload import EXECUTED_KEYS, UNEXECUTED_KEYS

TYPE = "manifest.files.types.*."
RULE = "file.rules.*."
VALUE = ("", ".*.template", ".*.normalize", ".*.normalize.*.replace", ".*.normalize.*.with")

#: Each key path the schemas gained with path values, sections, values, reshaping, on_miss and a
#: reference's skip list, or that ran on the to end of an edge only, and a declaration's has_child.
RUN = {
    *(f"{TYPE}path_values{k}" for k in (*VALUE, ".*.pattern", ".*.case")),
    *(f"{TYPE}sections{k}" for k in ("", ".*.name", ".*.open", ".*.close")),
    *(f"{RULE}values{k}" for k in (*VALUE, ".*.from", ".*.from.capture", ".*.case")),
    f"{RULE}match.reads_sections",
    f"{RULE}match.skip_names",
    f"{RULE}match.ending",
    f"{RULE}match.where.*.has_child",
    f"{RULE}emits.*.attribute.template",
    *(f"{RULE}emits.*.edge.{end}.on_miss" for end in ("from", "to")),
    *(f"{RULE}emits.*.edge.from{k}" for k in (".from", ".from.capture", ".template", ".type")),
    "manifest.tables",
    *(f"manifest.boundary{k}" for k in ("", ".*.type", ".*.ancestry", ".*.names")),
    *(
        f"{RULE}{holder}.resolve.*.lookup_last_segment_in"
        for holder in ("id", "emits.*.edge.from", "emits.*.edge.to")
    ),
    *(
        f"manifest.grammar.constant_access{k}"
        for k in ("", ".node", ".scope", ".name", ".enclosing")
    ),
    *(f"manifest.grammar.constant_declaration{k}" for k in ("", ".node", ".name", ".value")),
}


def test_each_key_this_order_runs_is_executed_and_not_reported() -> None:
    assert RUN <= EXECUTED_KEYS
    assert not RUN & set(UNEXECUTED_KEYS)


def test_a_value_from_any_source_but_a_capture_is_reported() -> None:
    """A value's ``from`` takes the id sources' vocabulary, and only ``capture`` runs."""
    reported = {p for p in UNEXECUTED_KEYS if p.startswith(f"{RULE}values.")}
    assert reported and all(p.startswith(f"{RULE}values.*.from.") for p in reported), reported
    assert f"{RULE}values.*.from.key" in reported
