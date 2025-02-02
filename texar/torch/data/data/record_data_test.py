"""
Unit tests for data related operations.
"""

import copy
import os
import shutil
import tempfile
import unittest

import numpy as np
import torch

from texar.torch.data.data.record_data import RecordData
from texar.torch.data.data.data_iterators import DataIterator
from texar.torch.data.data_utils import maybe_download
from texar.torch.utils import get_numpy_dtype


class RecordDataTest(unittest.TestCase):
    """Tests RecordData class.
    """

    def setUp(self):
        # Create test data
        self._test_dir = tempfile.mkdtemp()

        cat_in_snow = maybe_download(
            'https://storage.googleapis.com/download.tensorflow.org/'
            'example_images/320px-Felis_catus-cat_on_snow.jpg',
            self._test_dir, 'cat_0.jpg')
        williamsburg_bridge = maybe_download(
            'https://storage.googleapis.com/download.tensorflow.org/'
            'example_images/194px-New_East_River_Bridge_from_Brooklyn_'
            'det.4a09796u.jpg',
            self._test_dir, 'bridge_0.jpg')

        _feature_original_types = {
            'height': ('tf.int64', 'FixedLenFeature'),
            'width': ('tf.int64', 'FixedLenFeature'),
            'label': ('tf.int64', 'FixedLenFeature'),
            'shape': (np.int64, 'VarLenFeature'),
            'image_raw': (bytes, 'FixedLenFeature'),
            'variable1': (np.str, 'FixedLenFeature'),
            'variable2': ('tf.int64', 'FixedLenFeature'),
        }
        self._feature_convert_types = {
            'variable1': 'tf.float32',
            'variable2': 'tf.string',
        }
        _image_options = {}
        self._unconvert_features = ['height', 'width', 'label']

        self._dataset_valid = {
            'height': [],
            'width': [],
            'shape': [],
            'label': [],
            'image_raw': [],
            'variable1': [],
            'variable2': [],
        }
        _toy_image_labels_valid = {
            cat_in_snow: 0,
            williamsburg_bridge: 1,
        }
        _toy_image_shapes = {
            cat_in_snow: (213, 320, 3),
            williamsburg_bridge: (239, 194),
        }
        _tfrecord_filepath = os.path.join(self._test_dir, 'test.tfrecord')

        # Prepare Validation data
        with RecordData.writer(_tfrecord_filepath,
                                       _feature_original_types) as writer:
            for image_path, label in _toy_image_labels_valid.items():
                with open(image_path, 'rb') as fid:
                    image_data = fid.read()
                image_shape = _toy_image_shapes[image_path]

                # _construct_dataset_valid("", shape, label)
                single_data = {
                    'height': image_shape[0],
                    'width': image_shape[1],
                    'shape': image_shape,
                    'label': label,
                    'image_raw': image_data,
                    'variable1': "1234567890",
                    'variable2': int(9876543210),
                }
                for key, value in single_data.items():
                    self._dataset_valid[key].append(value)
                writer.write(single_data)

        self._hparams = {
            "num_epochs": 1,
            "batch_size": 1,
            "shuffle": False,
            "dataset": {
                "files": _tfrecord_filepath,
                "feature_original_types": _feature_original_types,
                "feature_convert_types": self._feature_convert_types,
                "image_options": [_image_options],
            }
        }

    def tearDown(self):
        """Remove the downloaded files after the test
        """
        shutil.rmtree(self._test_dir)

    def _run_and_test(self, hparams):
        # Construct database
        record_data = RecordData(hparams)
        iterator = DataIterator(record_data)

        def _prod(lst):
            res = 1
            for i in lst:
                res *= i
            return res

        for idx, data_batch in enumerate(iterator):
            self.assertEqual(
                set(data_batch.keys()),
                set(record_data.list_items()))

            # Check data consistency
            for key in self._unconvert_features:
                value = data_batch[key][0]
                self.assertEqual(value, self._dataset_valid[key][idx])
            self.assertEqual(
                list(data_batch['shape'][0]),
                list(self._dataset_valid['shape'][idx]))

            # Check data type conversion
            for key, item in self._feature_convert_types.items():
                dtype = get_numpy_dtype(item)
                value = data_batch[key][0]
                if dtype is np.str_:
                    self.assertIsInstance(value, str)
                elif dtype is np.bytes_:
                    self.assertIsInstance(value, bytes)
                else:
                    if isinstance(value, torch.Tensor):
                        value_dtype = get_numpy_dtype(value.dtype)
                    else:
                        value_dtype = value.dtype
                    dtype_matched = np.issubdtype(value_dtype, dtype)
                    self.assertTrue(dtype_matched)

            # Check image decoding and resize
            if hparams["dataset"].get("image_options"):
                image_options = hparams["dataset"].get("image_options")
                if isinstance(image_options, dict):
                    image_options = [image_options]
                for image_option_feature in image_options:
                    image_key = image_option_feature.get(
                        "image_feature_name")
                    if image_key is None:
                        continue
                    image_gen = data_batch[image_key][0]
                    image_valid_shape = self._dataset_valid["shape"][idx]
                    resize_height = image_option_feature.get(
                        "resize_height")
                    resize_width = image_option_feature.get(
                        "resize_width")
                    if resize_height and resize_width:
                        self.assertEqual(
                            image_gen.shape[0] * image_gen.shape[1],
                            resize_height * resize_width)
                    else:
                        self.assertEqual(
                            _prod(image_gen.shape),
                            _prod(image_valid_shape))

    def test_default_setting(self):
        """Tests the logics of TFRecordData.
        """
        self._run_and_test(self._hparams)

    def test_image_resize(self):
        """Tests the image resize function
        """
        hparams = copy.copy(self._hparams)
        _image_options = {
            'image_feature_name': 'image_raw',
            'resize_height': 512,
            'resize_width': 512,
        }
        hparams["dataset"].update({"image_options": _image_options})
        self._run_and_test(hparams)


if __name__ == "__main__":
    unittest.main()
