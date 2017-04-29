import abc
import threading
import Queue


class SimpleTask(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, inputs, task_id=None):
        self.inputs = inputs
        self.outputs = []
        self.task_id = task_id or id(self)
        self.size = 0
        self._event = threading.Event()
        self._offset = 0

    def request_inputs(self, size):
        self.size = min(size, len(self.inputs) - self._offset)
        inputs = self.inputs[self._offset:self._offset + self.size]
        self._offset += self.size
        return inputs

    def is_done(self):
        flag = (self._offset == len(self.inputs))
        if flag:
            self._event.set()
        return flag

    def eval(self, factory, time=False):
        if self.inputs:
            factory.queue.put(self)
            self._event.wait()
        return self.outputs


class BatchFactory(threading.Thread):
    __metaclass__ = abc.ABCMeta

    SERVE_FOREVER = True
    QUEUE_SIZE = 1024
    TIMEOUT = 0.001

    class TimeoutFunction(object):
        @staticmethod
        def CONSTANT(offset):
            def timeout_fn(size, batch_size):
                if size == 0:
                    return BatchFactory.TIMEOUT
                else:
                    return offset
            return timeout_fn

        @staticmethod
        def QUARDRATIC(offset, delta):
            def timeout_fn(size, batch_size):
                if size == 0:
                    return BatchFactory.TIMEOUT
                else:
                    return offset + delta * (1 - ((batch_size - 2 * float(size)) / batch_size) ** 2)
            return timeout_fn

    def __init__(self,
                 batch_size,
                 queue_size=QUEUE_SIZE,
                 timeout_fn=TimeoutFunction.CONSTANT(offset=0)):

        super(BatchFactory, self).__init__()

        self._stop = threading.Event()
        self.tasks = []
        self.batch_size = batch_size
        self.queue = Queue.Queue(maxsize=queue_size)
        self.timeout_fn = timeout_fn

    def stop(self):
        self._stop.set()

    @abc.abstractmethod
    def run_one(self, inputs):
        pass

    def run(self):
        while BatchFactory.SERVE_FOREVER:
            inputs = []

            # finish tasks at hand first ...
            for task in self.tasks:
                inputs.extend(task.request_inputs(size=self.batch_size - len(inputs)))

            # ... before retrieving new tasks
            while len(inputs) < self.batch_size:
                if self._stop.is_set():
                    return 0

                try:
                    task = self.queue.get(timeout=self.timeout_fn(len(inputs), self.batch_size))
                except Queue.Empty:
                    break
                else:
                    self.tasks.append(task)
                    inputs.extend(task.request_inputs(size=self.batch_size - len(inputs)))

            if len(inputs) == 0:
                continue

            try:
                outputs = self.run_one(inputs)
            # try one by one
            except Exception as e:
                print(e)
                outputs = []
                for input_ in inputs:
                    try:
                        output = self.run_one([input_])[0]
                    except Exception:
                        output = None

                    outputs.append(output)

            # do not remove in-place, dangerous!
            tasks_ = []
            for task in self.tasks:
                task.outputs.extend(outputs[:task.size])
                outputs = outputs[task.size:]

                if task.is_done():
                    self.queue.task_done()
                else:
                    tasks_.append(task)

            self.tasks = tasks_
