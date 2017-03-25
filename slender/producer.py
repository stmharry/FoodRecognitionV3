from __future__ import print_function

import numpy as np
import os
import sys
import tensorflow as tf

from .blob import Blob
from .util import scope_join_fn

_ = scope_join_fn('producer')


class BaseProducer(object):
    _CLASSNAME_NAME = 'class_names.txt'
    _BUFFER_CAPACITY = 256

    @staticmethod
    def queue_join(values_list, dtypes=None, shapes=None, enqueue_many=False, name='queue_join'):
        dtypes = dtypes or [value.dtype for value in values_list[0]]
        shapes = shapes or [value.get_shape()[enqueue_many:] for value in values_list[0]]

        queue = tf.FIFOQueue(
            capacity=BaseProducer._BUFFER_CAPACITY,
            dtypes=dtypes,
            shapes=shapes,
            name=name,
        )

        if enqueue_many:
            enqueue_fn = queue.enqueue_many
        else:
            enqueue_fn = queue.enqueue

        enqueue_list = [enqueue_fn(values) for values in values_list]
        queue_runner = tf.train.QueueRunner(queue, enqueue_list)
        tf.train.add_queue_runner(queue_runner)

        return queue

    def __init__(self,
                 working_dir,
                 image_dir=None,
                 batch_size=64):

        self.working_dir = working_dir
        self.classname_path = os.path.join(working_dir, BaseProducer._CLASSNAME_NAME)
        self.image_dir = image_dir
        self.batch_size = batch_size

        if os.path.isfile(self.classname_path):
            self.class_names = np.loadtxt(self.classname_path, dtype=np.str)
        else:
            self.class_names = np.sort([
                class_name
                for class_name in os.listdir(image_dir)
                if os.path.isdir(os.path.join(image_dir, class_name))
            ])
            np.savetxt(self.classname_path, self.class_names, fmt='%s')
        self.num_classes = len(self.class_names)


class LocalFileProducer(BaseProducer):
    class SubsampleFunction(object):
        @staticmethod
        def NO_SUBSAMPLE():
            def subsample(string):
                return True
            return subsample

        @staticmethod
        def HASH(mod, divisible):
            def subsample(string):
                return bool(hash(string) % mod) != divisible
            return subsample

    class MixScheme:
        NONE = 0
        UNIFORM = 1

    def __init__(self,
                 working_dir,
                 image_dir=None,
                 batch_size=64,
                 num_parallels=8,
                 subsample_fn=SubsampleFunction.NO_SUBSAMPLE(),
                 mix_scheme=MixScheme.NONE):

        super(LocalFileProducer, self).__init__(
            working_dir=working_dir,
            image_dir=image_dir,
            batch_size=batch_size,
        )

        self.filenames_by_subdir = {}
        for subdir_name in os.listdir(image_dir):
            self.filenames_by_subdir[subdir_name] = []

            subdir_path = os.path.join(image_dir, subdir_name)
            for (file_dir, _, file_names) in os.walk(subdir_path, followlinks=True):
                for file_name in file_names:
                    if file_name.startswith('.'):
                        continue
                    if not file_name.endswith('.jpg'):
                        continue
                    if not subsample_fn(file_name):
                        continue
                    self.filenames_by_subdir[subdir_name].append(os.path.join(file_dir, file_name))

        self.num_files = sum(map(len, self.filenames_by_subdir))
        self.num_batches_per_epoch = self.num_files // self.batch_size
        self.num_parallels = num_parallels
        self.subsample_fn = subsample_fn
        self.mix_scheme = mix_scheme

    def check(self):
        self.file_name = tf.placeholder(shape=(), dtype=tf.string)
        self.content = BaseProducer.read(self.file_name)
        self.image = tf.image.decode_jpeg(self.content)

        sess = tf.Session()

        for (num_subdir, (subdir_name, file_names)) in enumerate(self.filenames_by_subdir.items()):
            file_names_ = []
            for (num_file, file_name) in enumerate(file_names):
                print('Subdir {:s} ({:d}/{:d}), File {:s} ({:d}/{:d})'.format(
                    subdir_name,
                    num_subdir + 1,
                    len(self.filenames_by_subdir),
                    file_name,
                    num_file + 1,
                    len(file_names),
                ), end='\033[K\r')
                sys.stdout.flush()

                try:
                    image = sess.run(self.image, feed_dict={self.file_name: file_name})
                    assert image.ndim == 3 and image.shape[2] == 3
                except Exception:
                    print('Exception raised on {}'.format(file_name), end='\033[K\n')
                    os.remove(file_name)
                else:
                    file_names_.append(file_name)

            print('')

            self.filenames_by_subdir[dir_name] = file_names_

    def blob(self):
        with tf.variable_scope(_('blob')):
            if self.mix_scheme == LocalFileProducer.MixScheme.NONE:
                filename_labels = []
                for (subdir_name, file_names) in self.filenames_by_subdir.items():
                    if subdir_name in self.class_names:
                        label = self.class_names.index(subdir_name)
                    else:
                        label = -1

                    for file_name in file_names:
                        filename_labels.append((file_name, label))

                (file_names, labels) = zip(*filename_labels)

                labels = tf.convert_to_tensor(labels, dtype=tf.int64)
                file_names = tf.convert_to_tensor(file_names, dtype=tf.string)

            elif self.mix_scheme == LocalFileProducer.MixScheme.UNIFORM:
                assert set(self.filenames_by_subdir.keys()) == set(self.class_names)

                file_names = []
                for (subdir_name, file_names_) in self.filenames_by_subdir.items():
                    file_name_ = tf.train.string_input_producer(file_names_, name=subdir_name).dequeue()
                    file_names.append(file_name_)

                labels = tf.random_shuffle(tf.to_int64(tf.range(self.num_classes)))
                file_names = tf.gather(tf.pack(file_names), labels)

            filename_label_queue = BaseProducer.queue_join(
                [(file_names, labels)],
                enqueue_many=True,
            )

            filename_content_labels = []
            for num_parallel in xrange(self.num_parallels):
                (filename, label) = filename_label_queue.dequeue()
                filename_content_labels.append([
                    filename,
                    tf.read_file(filename),
                    label,
                ])

            filename_content_label_queue = BaseProducer.queue_join(filename_content_labels)
            (self.filenames, self.contents, self.labels) = filename_content_label_queue.dequeue_many(self.batch_size)

        return Blob(contents=self.contents, labels=self.labels)


class PlaceholderProducer(BaseProducer):
    def __init__(self,
                 working_dir,
                 batch_size=64):

        super(PlaceholderProducer, self).__init__(
            working_dir=working_dir,
            batch_size=batch_size,
        )

    def blob(self):
        with tf.variable_scope(_('blob')):
            self.contents = tf.placeholder(tf.string, shape=(None,))

            label_default = -1 * tf.ones_like(self.contents, dtype=tf.int64)
            self.labels = tf.placeholder_with_default(label_default, shape=(None,))

        return Blob(contents=self.contents, labels=self.labels)
