from core.contrib.detectors.base import Detector, FileType, DetectionResult
from core.datalayer import Datalayer
from core.models import BigFileStore
import os
from .errors import DetectionError
import json
import mimetypes

class BioimageExtensionDetector(Detector):



    def __init__(self) -> None:
        self.data_json_file = os.path.join(os.path.dirname(__file__), "bioimage_data.json")
        self.confidence_multiplier = 0.6
        
        super().__init__()


    
    def detect_mimetype(self, extensions: list[str]) -> str:
        for extension in extensions:
            if mimetypes.types_map.get(extension):
                return mimetypes.types_map.get(extension)
        return "unknown"



    def detect(self, store: BigFileStore, datalayer: Datalayer) -> DetectionResult:

        filename = store.key.split("/")[-1]
        print(f"Filename: {filename}")

        extension = filename.split(".")[-1]


        results = []


        for type in self.compiled_types:
            if extension in type.extensions:
                results.append(type)


        if len(results) == 0:
            raise DetectionError(f"Could not detect file extension {extension}")
        
        if len(results) == 1:
            return DetectionResult(
                name=results[0].name,
                score=1
            )
        
        # If there are multiple results, we adjust the confidence and
        # return the first result

        confidence = 1 / len(results) * self.confidence_multiplier

        return DetectionResult(
            name=results[0].name,
            score=confidence
        )


    def compile_types(self) -> list[FileType]:

        with open(self.data_json_file, "r") as f:
            content_type_json = json.load(f)
        

        types = []

        for key, value in content_type_json.items():
            
            types.append(FileType(
                name=key,
                description=value.get("description", ""),
                extensions=value.get("extensions", []),
                group=value.get("group", None),
                tags=value.get("tags", None),
                magic=value.get("magic", None),
                mime_type=value.get("mime_type", self.detect_mimetype(value.get("extensions", [])))
            ))

        return types
