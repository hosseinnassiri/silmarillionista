"""Allowed node labels and relationship types for graph extraction.

Kept intentionally constrained (per the plan) so LLMGraphTransformer doesn't
invent an unbounded vocabulary of ad-hoc labels/relations across 437 chunks.
"""

ALLOWED_NODES = [
    "Vala",
    "Maia",
    "Elf",
    "Man",
    "Dwarf",
    "Place",
    "Object",
    "Event",
    "House",
]

ALLOWED_RELATIONSHIPS = [
    "PARENT_OF",
    "SPOUSE_OF",
    "RULED",
    "CREATED",
    "DESTROYED",
    "FOUGHT",
    "ALLIED_WITH",
    "ENEMY_OF",
    "LOCATED_IN",
    "PARTICIPATED_IN",
    "ALSO_KNOWN_AS",
    "HAPPENED_DURING",
]
