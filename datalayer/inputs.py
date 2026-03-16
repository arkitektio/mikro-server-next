from datalayer import base_models
from strawberry.experimental import pydantic


@pydantic.input(model=base_models.RequestMediaUploadInput, all_fields=True)
class RequestMediaUploadInput:
    """
    Docstring for RequestMediaUploadInput
    """

    pass


@pydantic.input(model=base_models.FinishMediaUploadInput, all_fields=True)
class FinishMediaUploadInput:
    """
    Docstring for FinishMediaUploadInput
    """

    pass
