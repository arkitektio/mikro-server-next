from core.datalayer import Datalayer
from core.models import  BigFileStore
from .types import ContentModel
from .initialization import initialized_detectors, get_compiled_types
from datetime import datetime
import contextvars
from strawberry.extensions import SchemaExtension
from typing import Generator


class Inspector:


    def __init__(self) -> None:
        self.minimal_score = 0.90
        self.detectors = initialized_detectors
        self.compiled_types = get_compiled_types()



    def inspect_and_update(self, store: BigFileStore, datalayer: Datalayer) -> None:

        content_model = self.inspect_content(store, datalayer)

        store.content = content_model.dict()
        store.save()






    def inspect_content(self, store: BigFileStore, datalayer: Datalayer) -> ContentModel:
        
        for detector in self.detectors:
            try:
                result = detector.detect(store, datalayer)

                if result.score < self.minimal_score:
                    print("Score too low")
                    continue

                found_type = self.compiled_types.get(result.name)

                if not found_type:
                    raise Exception(f"Could not find type {result.name} in compiled types. Please check your detectors")
                

                return ContentModel(
                    content_type=found_type.name,
                    description=found_type.description or "No description",
                    mime_type=found_type.mime_type or "unknown",
                    score=result.score,
                    detection_method=detector.get_method_name(),
                    inspection_date=datetime.now()
                )

                
            
            except Exception as e:
                print(f"Detector {detector.get_method_name()} failed with error {e}")
                continue
        
        return ContentModel(
            content_type="unknown",
            score=0,
            mime_type="unknown",
            detection_method="failed",
            description="Unkown content type",
            inspection_date=datetime.now()
        )



    

    



current_inspector: contextvars.ContextVar["Inspector"] = contextvars.ContextVar("current_inspector")
inspector = Inspector()



def get_current_inspector() -> Inspector:
    return current_inspector.get()
    


class InspectorExtension(SchemaExtension):

    def on_operation(self) -> Generator[None, None, None]:
        t1 = current_inspector.set(
            inspector
        )
        
        yield
        current_inspector.reset(t1)

        print("GraphQL operation end")


