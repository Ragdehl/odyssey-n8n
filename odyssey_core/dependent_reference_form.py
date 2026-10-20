"""Conservative grammatical reference forms for Core cross-group handoffs.

This is a safety allowlist of closed-class anaphoric morphology, NOT a name
resolver, alias matcher, task parser, or claim that the pronoun has one target.
Semantic reviewers and physical Core receipt/CAS are still mandatory. Unknown
languages or uncommon referring descriptions abstain until typed proof exists.
"""

from __future__ import annotations

# Closed grammatical classes across the currently supported ES/FR/EN input.
# Do not admit arbitrary lower-case words: names can be lower-case in source.
_PRONOUNS = frozenset(
    "él ella ellos ellas le les lo los la las se sí ello esto eso aquello "
    "mismo misma mismos mismas ambos ambas uno una unos unas "
    "il ils elle elles lui eux leur leurs celui celle ceux celles ceci cela ça "
    "he she him her it they them himself herself themselves itself one ones "
    "this that these those".split()
)
_DETERMINERS = frozenset(
    "este esta estos estas ese esa esos esas aquel aquella aquellos aquellas ambos ambas "
    "el la los las un una unos unas su sus nuestro nuestra nuestros nuestras "
    "ce cet cette ces le la les son sa ses leur leurs "
    "the this that these those his her its their our".split()
)
_GENERIC_HEADS = frozenset(
    "persona personas hombre hombres mujer mujeres chico chica chicos chicas "
    "tarea tareas trabajo trabajos sesión sesiones nota notas documento documentos "
    "proyecto proyectos cosa cosas misma mismo primera primero segundo segunda "
    "person people man men woman women task tasks job jobs session sessions "
    "note notes document documents project projects one ones same first second "
    "personne personnes homme hommes femme femmes tâche tâches travail travaux "
    "séance séances document documents projet projets note notes même mêmes "
    "premier première deuxième".split()
)


def supported_anaphoric_form(mention: str) -> bool:
    """Return True for bounded grammatical anaphora, never for a guessed name.

    Deliberately exclude free descriptive phrases and unmatched aliases. False
    negatives yield clarification instead of linking a Task to the wrong Note.
    """
    if not isinstance(mention, str) or not mention or mention != mention.strip():
        return False
    words = mention.casefold().split()
    if len(words) == 1:
        return words[0] in _PRONOUNS
    if len(words) == 2:
        return words[0] in _DETERMINERS and words[1] in _GENERIC_HEADS
    return False
