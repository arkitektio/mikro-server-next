from core.contrib.detectors.base import Detector, FileType, DetectionResult
from core.datalayer import Datalayer
from core.models import BigFileStore
from .s3_magika import S3Magika
import re
from magika.content_types import CONTENT_TYPES_CONFIG_PATH
import json

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



class MagikaDetector(Detector):


    def detect(self, store: BigFileStore, datalayer: Datalayer) -> DetectionResult:
        """Detect the content of a file using magika

        Args:
            store (BigFileStore): The file store to inspect
            datalayer (Datalayer): The datalayer to use (where the file is stored)

        Returns:
            ContentModel: A model representing the content of the file
        """

        datalayer = Datalayer()

        m = S3Magika(file_system=datalayer.file_system)

        result =m.identify_path(f"/{store.bucket}/{store.key}")

        if result.output.ct_label is None:
            raise Exception("Could not detect content type")
        
        if result.output.ct_label == "null":
            raise Exception("Could not detect content type")
        
        if result.output.ct_label == "unknown":
            raise Exception("Could not detect content type")

        return DetectionResult(
            name=remove_special_chars(result.output.ct_label),
            score=result.output.score,
        )
    


    def compile_types(self) -> list[FileType]:

        with open(CONTENT_TYPES_CONFIG_PATH, "r") as f:
            content_type_json = json.load(f)
        

        types = []

        for key, value in content_type_json.items():
            if key == "null":
                continue


            types.append(FileType(
                name=remove_special_chars(key),
                description=value.get("description", ""),
                extensions=value.get("extensions", []),
                group=value.get("group", None),
                tags=value.get("tags", None),
                magic=value.get("magic", None),
                mime_type=value.get("mime_type", None)
            ))

        return types

