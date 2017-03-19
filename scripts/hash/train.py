#!/usr/bin/env python

import gflags
import sys

from slender.producer import LocalFileProducer as Producer
from slender.processor import TrainProcessor as Processor
from slender.net import HashNet, TrainScheme
from slender.util import new_working_dir

gflags.DEFINE_string('image_dir', None, 'Image directory')
gflags.DEFINE_string('working_dir_root', None, 'Root working directory')
gflags.DEFINE_integer('num_bits', 64, 'Number of bits')
gflags.DEFINE_integer('batch_size', 64, 'Batch size')
gflags.DEFINE_integer('subsample_ratio', 64, 'Training image subsample')
gflags.DEFINE_integer('num_epochs', 15, 'Run epoch count')
gflags.DEFINE_float('learning_rate', 0.1, 'Learning rate')
gflags.DEFINE_float('learning_rate_decay_epoch', 1.5, 'Learning rate decay epoch count')
gflags.DEFINE_float('learning_rate_decay_rate', 0.5, 'Learning rate decay rate')
gflags.DEFINE_float('softness', 1.0, 'Softness for tanh function')
gflags.DEFINE_float('softness_decay_epoch', 1.5, 'Softness decay epoch count')
gflags.DEFINE_float('softness_decay_rate', 1.0, 'Softness decay rate')
gflags.DEFINE_float('gpu_frac', 1.0, 'Fraction of GPU used')
FLAGS = gflags.FLAGS


class Net(HashNet, TrainScheme):
    pass


if __name__ == '__main__':
    FLAGS(sys.argv)
    working_dir = new_working_dir(FLAGS.working_dir_root)

    producer = Producer(
        image_dir=FLAGS.image_dir,
        working_dir=working_dir,
        batch_size=FLAGS.batch_size,
        subsample_fn=Producer.SubsampleFunction.HASH(mod=FLAGS.subsample_ratio, divisible=False),
        mix_scheme=Producer.MixScheme.UNIFORM,
    )
    processor = Processor()
    net = Net(
        working_dir=working_dir,
        num_bits=FLAGS.num_bits,
        learning_rate=FLAGS.learning_rate,
        learning_rate_decay_steps=FLAGS.learning_rate_decay_epoch * producer.num_batches_per_epoch,
        learning_rate_decay_rate=FLAGS.learning_rate_decay_rate,
        softness=FLAGS.softness,
        softness_decay_steps=FLAGS.softness_decay_epoch * producer.num_batches_per_epoch,
        softness_decay_rate=FLAGS.softness_decay_rate,
        gpu_frac=FLAGS.gpu_frac,
    )
    blob = (
        producer.blob()
        .f(processor.preprocess)
        .f(net.build)
    )
    if FLAGS.num_epochs > 0:
        net.run(FLAGS.num_epochs * producer.num_batches_per_epoch)
