from strawberry.experimental import pydantic
from pydantic import BaseModel
import strawberry
from enum import Enum
# Using regex to find all numbers in the input string
from typing import Optional
from .initialization import get_content_type_enum_values, get_detection_methods_enum_values
from datetime import datetime 



ContentTypeEnum = Enum("ContentType", get_content_type_enum_values())
ContentType = strawberry.enum(ContentTypeEnum, description="The type of content")

DetectionMethodEnum = Enum("DetectionMethod", get_detection_methods_enum_values())
DetectionMethod = strawberry.enum(DetectionMethodEnum, description="The method used to detect the content")



class ContentModel(BaseModel):
    content_type: ContentTypeEnum
    score: Optional[float]
    detection_method: DetectionMethodEnum
    description: str
    mime_type: str
    inspection_date: datetime

    class Config:
        use_enum_values = True



@pydantic.type(ContentModel)
class Content:
    content: str
    content_type: ContentType
    detection_method: DetectionMethod
    description: str
    score: float
    mime_type: str
    inspection_date: datetime
