"""Hand-written Cypher templates for known question shapes, used as a fallback
when LLM-generated Cypher returns zero records. LLM-generated Cypher can be
unreliable for these exact patterns (multi-hop family trees, allies-of-
enemies) even though they're extremely common question shapes with an
obvious, fixed translation to Cypher -- so a deterministic template beats
re-prompting an LLM that may or may not get the pattern right this time.

Order matters: more specific patterns (e.g. "allies of X's enemies") must be
checked before the general ones they'd otherwise be swallowed by (e.g.
"enemies of X").
"""

import re

_NAME = r"(.+?)"
_TRAIL = r"[?.!]*\s*$"

TEMPLATES: list[tuple[re.Pattern, str, str]] = [
    # compound two-hop patterns first
    (
        re.compile(rf"allies of {_NAME}'?s? enemies{_TRAIL}", re.I),
        "MATCH (p)-[:ENEMY_OF]-(enemy)-[:ALLIED_WITH]-(ally) "
        "WHERE apoc.text.clean(p.id) = apoc.text.clean($name) "
        "RETURN DISTINCT ally.id AS ally",
        "enemies_allies",
    ),
    (
        re.compile(rf"enemies of {_NAME}'?s? allies{_TRAIL}", re.I),
        "MATCH (p)-[:ALLIED_WITH]-(ally)-[:ENEMY_OF]-(enemy) "
        "WHERE apoc.text.clean(p.id) = apoc.text.clean($name) "
        "RETURN DISTINCT enemy.id AS enemy",
        "allies_enemies",
    ),
    # family tree
    (
        re.compile(rf"descendants? of {_NAME}{_TRAIL}", re.I),
        "MATCH (p)-[:PARENT_OF*1..]->(d) "
        "WHERE apoc.text.clean(p.id) = apoc.text.clean($name) "
        "RETURN DISTINCT d.id AS descendant",
        "descendants",
    ),
    (
        re.compile(rf"(?:children|sons|daughters) of {_NAME}{_TRAIL}", re.I),
        "MATCH (p)-[:PARENT_OF]->(c) "
        "WHERE apoc.text.clean(p.id) = apoc.text.clean($name) "
        "RETURN c.id AS child",
        "children",
    ),
    # aliases
    (
        re.compile(
            rf"(?:aliases|other names|also known as) (?:of|does) {_NAME}(?: have)?{_TRAIL}", re.I
        ),
        "MATCH (p)-[:ALSO_KNOWN_AS]-(alias) "
        "WHERE apoc.text.clean(p.id) = apoc.text.clean($name) "
        "RETURN DISTINCT alias.id AS alias",
        "aliases",
    ),
    (
        re.compile(rf"(?:what is|who is) {_NAME} also known as{_TRAIL}", re.I),
        "MATCH (p)-[:ALSO_KNOWN_AS]-(alias) "
        "WHERE apoc.text.clean(p.id) = apoc.text.clean($name) "
        "RETURN DISTINCT alias.id AS alias",
        "aliases_reversed",
    ),
    # single-hop allies/enemies (checked last so the two-hop patterns above win)
    (
        re.compile(rf"allies of {_NAME}{_TRAIL}", re.I),
        "MATCH (p)-[:ALLIED_WITH]-(ally) "
        "WHERE apoc.text.clean(p.id) = apoc.text.clean($name) "
        "RETURN DISTINCT ally.id AS ally",
        "allies",
    ),
    (
        re.compile(rf"enemies of {_NAME}{_TRAIL}", re.I),
        "MATCH (p)-[:ENEMY_OF]-(enemy) "
        "WHERE apoc.text.clean(p.id) = apoc.text.clean($name) "
        "RETURN DISTINCT enemy.id AS enemy",
        "enemies",
    ),
]


_LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+", re.I)


def match_template(question: str) -> tuple[str, dict, str] | None:
    """Returns (cypher, params, template_name) if the question matches a known
    shape, else None."""
    for pattern, cypher, name in TEMPLATES:
        m = pattern.search(question)
        if m:
            entity_name = m.group(1).strip(" ?.!'\"")
            entity_name = _LEADING_ARTICLE.sub("", entity_name)
            return cypher, {"name": entity_name}, name
    return None
