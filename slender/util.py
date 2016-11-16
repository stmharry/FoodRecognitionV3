import os
import tensorflow as tf
import time


''' Directory
'''
def new_working_dir(working_dir_root):
    working_dir = os.path.join(working_dir_root, time.strftime('%Y-%m-%d-%H%M%S'))
    os.makedirs(working_dir)
    return working_dir


def latest_working_dir(working_dir_root):
    working_dirs = [os.path.join(working_dir_root, dir_) for dir_ in os.listdir(working_dir_root)]
    working_dir = max(working_dirs, key=os.path.getmtime)
    return working_dir

''' Scope
'''
def scope_join_fn(scope):
    def scope_join(*args):
        return os.path.join(scope, *args)
    return scope_join


''' DEBUG
'''
def LOG(value, name=None, fn=tf.identity):
    value = tf.Print(value, [fn(value)], '{}: '.format(name or value.__name__))
    return value
