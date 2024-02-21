from core.contrib.detectors.base import Detector, FileType
from core.contrib.detectors.magika.detector import MagikaDetector
from core.contrib.detectors.bioimage import BioimageExtensionDetector
from django.conf import settings
import strawberry



def get_detectors() -> list[Detector]:
    print(settings.DETECTORS)
    return [MagikaDetector(), BioimageExtensionDetector()]





initialized_detectors = get_detectors()


def get_compiled_types() -> dict[str, FileType]:
    compiled_types = {}

    for detector in initialized_detectors:
        for file_type in detector.compiled_types:
            if file_type.name not in compiled_types:
                compiled_types[file_type.name] = file_type
            else:
                print(f"Duplicate file type {file_type.name} found in detectors {detector.get_method_name()} and {compiled_types[file_type.name]}")


    return compiled_types



def get_content_type_enum_values() -> dict[str, strawberry.enum_value]:
    file_types = {}

    for detector in initialized_detectors:
        for file_type in detector.compiled_types:
            file_types[file_type.name] = strawberry.enum_value(file_type.name, description=file_type.description)

    return file_types



def get_detection_methods_enum_values():

    methods = {"failed": strawberry.enum_value("failed", description="Failed to detect content type"), "not_detected": strawberry.enum_value("not_detected", description="Content type never detected")}

    for detector in initialized_detectors:
        methods[detector.get_method_name()] = strawberry.enum_value(detector.get_method_name(), description=detector.get_method_name())

    return methods




