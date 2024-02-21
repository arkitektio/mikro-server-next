from typing import Optional
from pydantic import BaseModel
from core.datalayer import Datalayer
from core.models import BigFileStore

class FileType(BaseModel):
    name: str
    
    extensions: list[str]
    description: Optional[str] = None
    group: Optional[str] = None
    tags: Optional[list[str]] = None
    magic: Optional[str] = None
    mime_type: Optional[str] = None




class DetectionResult(BaseModel):
    name: str
    score: float




    

class Detector:


    def __init__(self) -> None:
        super().__init__()
        self.compiled_types = self.compile_types()


    def detect(self, store: BigFileStore, datalayer: Datalayer) -> DetectionResult:
        raise NotImplementedError("Detector must implement detect method")

    def compile_types(self) -> list[FileType]:
        raise NotImplementedError("Detector must implement compile_types method")

    def get_method_name(self) -> str:
        return self.__class__.__name__.lower().replace("detector", "")
    

    
