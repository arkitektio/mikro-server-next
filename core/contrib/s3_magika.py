from magika import Magika
from magika.content_types import ContentType
from magika.types import ModelFeatures, MagikaResult
from s3fs import S3FileSystem
from typing import Any, Optional, Tuple

class S3Magika(Magika):

    def __init__(self, *args: Any, file_system: Optional[S3FileSystem] = None,  **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        assert file_system is not None, "file_system is required for this test"
        self._file_system = file_system


    def _extract_features_from_path(
        self,
        file_path: str,
        beg_size: Optional[int] = None,
        mid_size: Optional[int] = None,
        end_size: Optional[int] = None,
        padding_token: Optional[int] = None,
    ) -> ModelFeatures:
        # Note: it is critical that this reflects exactly how we are extracting
        # features for training.

        # Ideally, we should seek around the file instead of reading the full
        # content. In practice, however, this is not trivial as we need to strip
        # whitespace-like characters first. Now, it's possible to code something
        # like this in a simple way, but it turns out it's challenging to write
        # a seek-only algorithm that is 100% the same as how we extracted
        # features during training. For example, consider a 129-byte file with
        # 128 ASCII letters + a space, and beg feature size of 512. Let's say
        # you read the first 129 characters, the question is: what should you do
        # with the trailing space? We know we should strip it, but that's the
        # case only because it's the end of the file and there are no other
        # non-whitespace characters left. In the general case, this means we
        # would need to read more bytes (more than 129) to determine what to do
        # with the trailing space (whether to keep it or to strip + consider it
        # as padding).  For all these reasons, for now we implement the exact
        # clone of what we do for features extraction, even if not ideal.

        if beg_size is None:
            beg_size = self._input_sizes["beg"]
        if mid_size is None:
            mid_size = self._input_sizes["mid"]
        if end_size is None:
            end_size = self._input_sizes["end"]
        if padding_token is None:
            padding_token = self._padding_token

        assert beg_size <= 512
        assert mid_size <= 512
        assert end_size <= 512

        block_size = 4096

        file_size = self._file_system.stat(file_path)["size"]

        if file_size < 2 * block_size:
            # fast path for small files
            with self._file_system.open(file_path, "rb") as f:
                content = f.read()
            return self._extract_features_from_bytes(
                content, beg_size, mid_size, end_size, padding_token
            )
        else:
            # avoid reading the entire file
            with self._file_system.open(file_path, "rb") as f:
                if beg_size > 0:
                    beg_full = f.read(block_size)
                    beg_full_orig_size = len(beg_full)
                    beg_full = beg_full.lstrip()
                    beg_trimmed_size = beg_full_orig_size - len(beg_full)
                    if len(beg_full) < beg_size:
                        # Note that this is an approximation with respect what we do
                        # at feature extraction. What we do is different if, for
                        # example, the first two blocks of content are whitespaces:
                        # for feature extraction, we would keep reading content,
                        # while here we stop after two blocks.
                        beg_full += f.read(block_size)
                    beg = beg_full[:beg_size]
                else:
                    beg = b""
                    beg_trimmed_size = 0

                if end_size > 0:
                    f.seek(-block_size, 2)  # whence = 2: end of the file
                    end_full = f.read(block_size)
                    end_full_orig_size = len(end_full)
                    end_full = end_full.rstrip()
                    end_trimmed_size = end_full_orig_size - len(end_full)
                    if len(end_full) < end_size:
                        # Same as above
                        f.seek(-2 * block_size, 2)  # whence = 2: end of the file
                        end_full = f.read(block_size) + end_full
                    end = end_full[-end_size:]
                else:
                    end = b""
                    end_trimmed_size = 0

                if mid_size > 0:
                    mid_idx = (file_size - beg_trimmed_size - end_trimmed_size) // 2
                    mid_left_idx = mid_idx - mid_size // 2
                    f.seek(mid_left_idx, 0)  # whence = 0: start of the file
                    mid = f.read(mid_size)
                else:
                    mid = b""

            beg_ints = list(map(int, beg))
            mid_ints = list(map(int, mid))
            end_ints = list(map(int, end))

        assert len(beg_ints) == beg_size
        assert len(mid_ints) == mid_size
        assert len(end_ints) == end_size

        return ModelFeatures(beg=beg_ints, mid=mid_ints, end=end_ints)
    
    def _get_result_or_features_from_path(
        self, path: str
    ) -> Tuple[Optional[MagikaResult], Optional[ModelFeatures]]:
        """
        Given a path, we return either a MagikaOutput or a MagikaFeatures.

        There are some files and corner cases for which we do not need to use
        deep learning to get the output; in these cases, we already return a
        MagikaOutput object.

        For some other files, we do need to use deep learning, in which case we
        return a MagikaFeatures object. Note that for now we just collect the
        features instead of already performing inference because we want to use
        batching.
        """

        if not self._file_system.exists(path):
            result = self._get_result_from_labels_and_score(
                path,
                dl_ct_label=None,
                output_ct_label=ContentType.FILE_DOES_NOT_EXIST,
                score=1.0,
            )
            return result, None

        if self._file_system.isfile(path):



            if self._file_system.stat(path)["size"] == 0:
                result = self._get_result_from_labels_and_score(
                    path, dl_ct_label=None, output_ct_label=ContentType.EMPTY, score=1.0
                )
                return result, None

            # elif not os.access(path, os.R_OK):
            #     result = self._get_result_from_labels_and_score(
            #         path,
            #         dl_ct_label=None,
            #         output_ct_label=ContentType.PERMISSION_ERROR,
            #         score=1.0,
            #     )
            #     return result, None

            elif self._file_system.stat(path)["size"] <= self._min_file_size_for_dl:
                result = self._get_result_of_small_file(path)
                return result, None

            else:
                file_features = self._extract_features_from_path(path)
                # Check whether we have enough bytes for a meaningful
                # detection, and not just padding.
                if (
                    file_features.beg[self._min_file_size_for_dl - 1]
                    == self._padding_token
                ):
                    # If the n-th token is padding, then it means that,
                    # post-stripping, we do not have enough meaningful
                    # bytes.
                    result = self._get_result_of_small_file(path)
                    return result, None

                else:
                    # We have enough bytes, scheduling this file for model
                    # prediction.
                    # features.append((path, file_features))
                    return None, file_features

        elif self._file_system.isdir(path):
            result = self._get_result_from_labels_and_score(
                path, dl_ct_label=None, output_ct_label=ContentType.DIRECTORY, score=1.0
            )
            return result, None

        else:
            result = self._get_result_from_labels_and_score(
                path, dl_ct_label=None, output_ct_label=ContentType.UNKNOWN, score=1.0
            )
            return result, None

        raise Exception("unreachable")