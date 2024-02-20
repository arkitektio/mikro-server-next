from core.datalayer import Datalayer
from core.models import File, BigFileStore
from .s3_magika import S3Magika
from .magic_types import ContentModel

def inspect_content(store: BigFileStore, datalayer: Datalayer) -> ContentModel:
    """
    Inspect the content of a file

    Args:
    - path: the path of the file to inspect
    - datalayer: the datalayer to use

    Returns:
    - Content: the content of the file
    """


    datalayer = Datalayer()

    m = S3Magika(file_system=datalayer.file_system)

    result =m.identify_path(f"/{store.bucket}/{store.key}")

    assert result.output.mime_type == "image/tiff"

    return ContentModel.from_magika_result(result)