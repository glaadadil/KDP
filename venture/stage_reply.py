"""Exchange format between a ChatGPT discussion and an individual workshop mission."""
import json
import re
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, ValidationError, field_validator, model_validator

from .models import Kind, Strict

PROTOCOL = "venture.stage.v1"
MAX_RESPONSE = 280_000
MetadataField = Literal["title", "subtitle", "description", "category", "keywords"]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class MetadataSuggestions(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    category: str | None = Field(default=None, min_length=1, max_length=250)
    keywords: list[Keyword] | None = Field(default=None, min_length=1, max_length=40)

    @model_validator(mode="before")
    @classmethod
    def reject_null_suggestions(cls, value):
        if isinstance(value, dict) and any(v is None for v in value.values()):
            raise ValueError("Omettre les suggestions sans valeur.")
        return value


class StageReply(Strict):
    protocol: Literal["venture.stage.v1"]
    edition_id: str = Field(min_length=1, max_length=80)
    stage: str = Field(min_length=1, max_length=60)
    deliverable: str = Field(min_length=1, max_length=120_000)
    handoff: str = Field(min_length=1, max_length=1100)
    decisions: list[Note] = Field(default_factory=list, max_length=12)
    open_questions: list[Note] = Field(default_factory=list, max_length=12)
    sources: list[Note] = Field(default_factory=list, max_length=12)
    checks: list[Note] = Field(default_factory=list, max_length=12)
    suggested_metadata: MetadataSuggestions = Field(default_factory=MetadataSuggestions)


class RawStageReply(Strict):
    response: str = Field(min_length=1, max_length=MAX_RESPONSE)


class ApplySuggestions(Strict):
    fields: list[MetadataField] = Field(min_length=1, max_length=5)

    @field_validator("fields")
    @classmethod
    def unique_fields(cls, fields):
        if len(fields) != len(set(fields)):
            raise ValueError("Sélectionne chaque champ une seule fois.")
        return fields


class WorkshopKind(Strict):
    kind: Kind | None


def reply_template(project_id, stage_name):
    return {
        "protocol": PROTOCOL,
        "edition_id": project_id,
        "stage": stage_name,
        "deliverable": "",
        "handoff": "",
        "decisions": [],
        "open_questions": [],
        "sources": [],
        "checks": [],
        "suggested_metadata": {},
    }


def _unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Deux champs JSON portent le même nom.")
        obj[key] = value
    return obj


def _reject_constant(_):
    raise ValueError("Les nombres doivent être valides en JSON.")


def _extract_json(text):
    text = text.strip().lstrip("\ufeff").strip()
    if text.startswith("{"):
        return text
    fences = list(re.finditer(r"(?m)^[ \t]*(`{3,})([a-zA-Z]*)[ \t]*\r?$", text))
    if len(fences) == 2:
        start, end = fences
        if (start.group(2).lower() in ("", "json")
            and not end.group(2)
            and start.group(1) == end.group(1)
            and len(text[:start.start()]) + len(text[end.end():]) <= 1200
            and not re.search(r"[{}]", text[:start.start()] + text[end.end():])):
            return text[start.end():end.start()].strip()
    raise ValueError("Colle une seule réponse JSON de l’Atelier ou utilise la conversion d’un texte existant.")


def parse_reply(text, project_id, stage_name):
    if len(text) > MAX_RESPONSE:
        raise ValueError("La réponse dépasse la taille autorisée.")
    try:
        payload = json.loads(_extract_json(text), object_pairs_hook=_unique_keys, parse_constant=_reject_constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("JSON incomplet ou illisible. Demande à ChatGPT de renvoyer l’objet JSON complet.") from exc
    try:
        parsed = StageReply.model_validate(payload, strict=True)
    except ValidationError as exc:
        names = ", ".join(".".join(map(str, error["loc"])) or "racine" for error in exc.errors()[:5])
        raise ValueError("Format de réponse invalide. Vérifie les champs obligatoires, les types et les limites : " + names) from exc
    if parsed.edition_id != project_id:
        raise ValueError("Cette réponse appartient à une autre édition. Copie la mission de cette édition.")
    if parsed.stage != stage_name:
        raise ValueError(f"Cette réponse correspond à une autre étape. Étape attendue : {stage_name}.")
    return parsed.model_dump(exclude_none=True)
