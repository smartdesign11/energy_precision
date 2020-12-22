# -*- coding: utf-8 -*-

# @Time  : 2020/10/14 下午8:51
# @Author : fl
# @Project : energy_prediction
# @FileName: client

import random
import warnings
import numpy as np


class Client:

    def __init__(self, client_id, group=None, train_data=None, eval_data=None, model=None):
        if eval_data is None:
            eval_data = {'x': [], 'y': []}
        if train_data is None:
            train_data = {'x': [], 'y': []}

        self._model = model
        self.id = client_id
        self.group = group
        self.train_data = train_data
        self.eval_data = eval_data

    def train(self, num_epochs=1, batch_size=10, minibatch=None):
        """使用训练数据来训练自己的模型.

        Args:
            num_epochs: Number of epochs to train. Unsupported if minibatch is provided (minibatch has only 1 epoch)
            batch_size: Size of training batches.
            minibatch: fraction of client's data to apply minibatch sgd,
                None to use FedAvg
        Return:
            comp: number of FLOPs executed in training process
            num_samples: number of samples used in training
            update: set of weights
            update_size: number of bytes in update
        """
        if minibatch is None:
            data = self.train_data
            comp, update = self.model.train(data, num_epochs, batch_size)
        else:
            frac = min(1.0, minibatch)
            num_data = max(1, int(frac * len(self.train_data["x"])))
            xs, ys = zip(*random.sample(list(zip(self.train_data["x"], self.train_data["y"])), num_data))
            data = {'x': xs, 'y': ys}

            # Minibatch trains for only 1 epoch - multiple local epochs don't make sense!
            num_epochs = 1
            comp, update = self.model.train(data, num_epochs, num_data)
        num_train_samples = len(data['y'])
        return comp, num_train_samples, update

    def test(self, set_to_use='test'):
        """使用测试数据来测试模型.

        Args:
            set_to_use. Set to test on. Should be in ['train', 'test'].
        Return:
            dict of metrics returned by the model.
        """
        assert set_to_use in ['train', 'test']
        if set_to_use == 'train':
            data = self.train_data
        else:
            data = self.eval_data
        return self.model.test(data)

    @property
    def num_test_samples(self):
        """客户端的测试数据量.

        Return:
            int: Number of test samples for this client
        """
        if self.eval_data is None:
            return 0
        return len(self.eval_data['y'])

    @property
    def num_train_samples(self):
        """客户端的训练数据量.

        Return:
            int: Number of train samples for this client
        """
        if self.train_data is None:
            return 0
        return len(self.train_data['y'])

    @property
    def num_samples(self):
        """客户端的总数据量.

        Return:
            int: Number of samples for this client
        """
        train_size = 0
        if self.train_data is not None:
            train_size = len(self.train_data['y'])

        test_size = 0
        if self.eval_data is not None:
            test_size = len(self.eval_data['y'])
        return train_size + test_size

    @property
    def model(self):
        """返回客户端的训练模型"""
        return self._model

    @model.setter
    def model(self, model):
        warnings.warn('The current implementation shares the model among all clients.'
                      'Setting it on one client will effectively modify all clients.')
        self._model = model
