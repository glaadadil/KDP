from pathlib import PurePosixPath
import re
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Channel = Literal["etsy", "paper", "kindle"]
Role = Literal["client", "notice", "preview", "interior", "cover", "ebook", "source", "pending"]
Kind = Literal["livre", "outil", "imprimable"]
CHANNELS = {"etsy": "Etsy numérique", "paper": "KDP broché", "kindle": "Kindle eBook"}
ROLES = {"pending": "À identifier", "client": "Fichier client", "notice": "Notice client", "preview": "Image commerciale", "interior": "Intérieur PDF", "cover": "Couverture", "ebook": "Manuscrit EPUB", "source": "Source de travail"}
STATES = ["Brouillon", "Prêt au dépôt", "Dépôt en cours", "Soumis", "En examen", "Publié", "Correction nécessaire"]
ALLOWED = {".pdf", ".png", ".jpg", ".jpeg", ".zip", ".epub", ".xlsx", ".ods", ".txt", ".md", ".csv", ".docx"}
def uid():
    return str(uuid4())

def filename(value):
    if (not value or len(value)>180 or PurePosixPath(value).name != value or re.search(r'[<>:"/\\|?*\x00-\x1f]', value)
        or value.endswith((" ", ".")) or value.startswith(".") or value.split(".")[0].upper() in {"CON","PRN","AUX","NUL",*(f"COM{i}" for i in range(10)),*(f"LPT{i}" for i in range(10))}):
        raise ValueError("Nom de fichier incompatible avec Windows.")
    return value

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

class Expected(Strict):
    name: str
    role: Role
    _name = field_validator("name")(filename)

class PrintOptions(Strict):
    trim: Literal["5x8","5.5x8.5","6x9","7x10","8x10"]="6x9"
    paper: Literal["white","cream","standard-color","premium-color"]="white"
    bleed: bool=False

class Manifest(Strict):
    schema_version: Literal["1.0"]
    product_id: str = Field(default_factory=uid, pattern=r'^[A-Za-z0-9_-]{1,80}$')
    title: str=Field(min_length=1,max_length=200)
    kind: Kind
    channel: Channel
    version: str=Field(min_length=1,max_length=40)
    language: str=Field(default="en",min_length=2,max_length=40)
    brief: str=Field(default="",max_length=10000)
    subtitle: str=Field(default="",max_length=200)
    author: str=Field(default="",max_length=150)
    description: str=Field(default="",max_length=10000)
    keywords: list[str]=Field(default_factory=list,max_length=40)
    category: str=Field(default="",max_length=250)
    price: float|None=Field(default=None,gt=0,le=1000000)
    currency: str=Field(default="USD",pattern=r"^[A-Z]{3}$")
    ai: Literal["unknown","none","assisted","generated"]="unknown"
    ai_details: str=Field(default="",max_length=1000)
    print: PrintOptions=Field(default_factory=PrintOptions)
    expected: list[Expected]=Field(default_factory=list,max_length=100)
    declared_checks: list[str]=Field(default_factory=list,max_length=100)
    declared_validations: list[str]=Field(default_factory=list,max_length=100)
    @model_validator(mode="after")
    def coherent(self):
        names=[f.name.casefold() for f in self.expected]
        if len(set(names))!=len(names):
            raise ValueError("Le manifeste contient plusieurs rôles pour un même nom.")
        if any(not s.strip() or len(s)>150 for s in self.keywords):
            raise ValueError("Mot-clé vide ou trop long.")
        if any(PurePosixPath(f.name).suffix.lower() not in ALLOWED for f in self.expected):
            raise ValueError("Une extension attendue est incompatible.")
        return self

class RoleChange(Strict):
    role: Role
class Result(Strict):
    text: str=Field(default="",max_length=120000)
    response: str | None = Field(default=None, min_length=1, max_length=280000)
    notes: str=Field(default="",max_length=10000)
    decision: Literal["draft","approve","revise"]
class Publication(Strict):
    state: Literal["Dépôt en cours","Soumis","En examen","Publié","Correction nécessaire"]
    reference: str=Field(default="",max_length=300)
    confirmed: Literal[True]
class Edition(Strict):
    channel: Channel
    version: str=Field(min_length=1,max_length=40)
