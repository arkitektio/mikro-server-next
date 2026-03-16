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


@pydantic.input(model=base_models.RequestBigFileUploadInput, all_fields=True)
class RequestBigFileUploadInput:
    """
    Docstring for RequestMediaUploadInput
    """

    pass


@pydantic.input(model=base_models.FinishBigFileUploadInput, all_fields=True)
class FinishBigFileUploadInput:
    """
    Docstring for FinishMediaUploadInput
    """

    pass


@pydantic.input(model=base_models.RequestZarrUploadInput, all_fields=True)
class RequestZarrUploadInput:
    """
    Docstring for RequestZarrUploadInput
    """

    pass


@pydantic.input(model=base_models.FinishZarrUploadInput, all_fields=True)
class FinishZarrUploadInput:
    """
    Docstring for FinishZarrUploadInput
    """

    pass


@pydantic.input(model=base_models.RequestParquetUploadInput, all_fields=True)
class RequestParquetUploadInput:
    """
    Docstring for RequestParquetUploadInput
    """

    pass


@pydantic.input(model=base_models.FinishParquetUploadInput, all_fields=True)
class FinishParquetUploadInput:
    """
    Docstring for FinishParquetUploadInput
    """

    pass
