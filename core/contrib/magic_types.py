from strawberry.experimental import pydantic
from pydantic import BaseModel
import strawberry
from magika.content_types import CONTENT_TYPES_CONFIG_PATH
import json
from enum import Enum
from magika.content_types import ContentType
from magika.types import ModelFeatures, MagikaResult
# Using regex to find all numbers in the input string
import re



conversion = {
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
    "0": "zero"
}


def replace_numbers_with_words(s: re.Match[str]) -> str:
    string = "".join([conversion[char] for char in s.group()])
    return string


def remove_special_chars(s: str) -> str:

    pattern = r'\d+'
    
    # Replacing all found numbers with their words
    return re.sub(pattern, replace_numbers_with_words, s)


def compile_magic_types() -> dict[str, str]:
    with open(CONTENT_TYPES_CONFIG_PATH, "r") as f:
        content_type_json = json.load(f)


    names = {key: remove_special_chars(key) for key in content_type_json.keys()}

    if "null" in names:
        del names["null"]




    return names

magika_map = compile_magic_types()
MagikaTypeEnum = Enum("MagikaType", {value: value for value in magika_map.values()})


def get_enum_value(magika_type: str) -> MagikaTypeEnum:
    return MagikaTypeEnum[magika_map[magika_type]]


MagikaType = strawberry.enum(MagikaTypeEnum)






class ContentModel(BaseModel):
    content: str
    magica_type: MagikaTypeEnum
    score: float
    group: str
    mime_type: str
    magic: str
    description: str

    
    @classmethod
    def from_magika_result(cls, result: MagikaResult) -> "ContentModel":
        return cls(
            content=result.path,
            magica_type=get_enum_value(result.dl.ct_label),
            score=result.dl.score,
            group=result.output.group,
            mime_type=result.output.mime_type,
            magic=result.output.magic,
            description=result.output.description
        )


@pydantic.type(ContentModel)
class Content:
    content: str
    magica_type: MagikaType
    score: float
    group: str
    mime_type: str
    magic: str
    description: str
