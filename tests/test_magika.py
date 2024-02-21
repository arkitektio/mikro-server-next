from magika import Magika
from django.conf import settings
from .constants import TEST_BUCKET_NAME
from core.datalayer import Datalayer




def test_inspect_file() -> None:

    file_dir = settings.DEMOS_DIR / "cells1.tiff"

    m = Magika()

    assert m.identify_path(file_dir).output.mime_type == "image/tiff"





def test_bucket_creation() -> None:

    file_dir = settings.DEMOS_DIR / "cells1.tiff"


    datalayer = Datalayer()

    s3 = datalayer.s3

    s3.create_bucket(Bucket=settings.FILE_BUCKET)




    s3.upload_file(file_dir, TEST_BUCKET_NAME, "cells1.tiff")


    







