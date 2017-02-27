#!/usr/bin/env python

import gflags
import sys

from slender.producer import LocalFileProducer as Producer
from slender.processor import TrainProcessor as Processor
from slender.net import TrainClassifyNet as Net
from slender.util import new_working_dir

gflags.DEFINE_string('image_dir', None, 'Image directory')
gflags.DEFINE_string('working_dir_root', None, 'Root working directory')
gflags.DEFINE_integer('batch_size', 64, 'Batch size')
gflags.DEFINE_integer('num_epochs', 15, 'Run epoch count')
gflags.DEFINE_float('learning_rate', 0.1, 'Learning rate')
gflags.DEFINE_float('learning_rate_decay_epoch', 1.5, 'Learning rate decay epoch count')
gflags.DEFINE_float('learning_rate_decay_rate', 0.5, 'Learning rate decay rate')
gflags.DEFINE_float('gpu_frac', 1.0, 'Fraction of GPU used')
FLAGS = gflags.FLAGS


if __name__ == '__main__':
    FLAGS(sys.argv)
    working_dir = new_working_dir(FLAGS.working_dir_root)

    producer = Producer(
        image_dir=FLAGS.image_dir,
        working_dir=working_dir,
        batch_size=FLAGS.batch_size,
        subsample_fn=Producer.SubsampleFunction.HASH(mod=64, divisible=False),
        mix_scheme=Producer.MixScheme.UNIFORM,
    )
    processor = Processor()
    net = Net(
        working_dir=working_dir,
        num_classes=producer.num_classes,
        learning_rate=FLAGS.learning_rate,
        learning_rate_decay_steps=FLAGS.learning_rate_decay_epoch * producer.num_batches_per_epoch,
        learning_rate_decay_rate=FLAGS.learning_rate_decay_rate,
        gpu_frac=FLAGS.gpu_frac,
    )
    blob = (
        producer.blob()
        .f(processor.preprocess)
        .f(net.build)
    )
    if FLAGS.num_epochs:
        net.run(FLAGS.num_epochs * producer.num_batches_per_epoch)
