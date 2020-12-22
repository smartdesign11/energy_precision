# -*- coding: utf-8 -*-

# @Time  : 2020/10/14 晚上10:00
# @Author : fl
# @Project : energy_prediction
# @FileName: prediction.py

import os
import numpy as np
import random
import tensorflow as tf
import time

from prediction.client import Client
from prediction.server import Server
from prediction.model.lstm import LSTMModel
import prediction.metrics.writer as metrics_writer
from prediction.utils.model_utils import read_data

class Prediction:
    def __init__(self, config, details=False):
        """
        针对居民用电量预测的顶级类
        Args:
            config_path(str): 配置文件

        """

        self.config = config

    def run(self, model_type='LSTM'):
        random_seed = self.config.random_seed
        # 设置随机数种子
        random.seed(1 + random_seed)
        np.random.seed(12 + random_seed)
        tf.set_random_seed(123 + random_seed)
        # 屏蔽tf警告
        tf.logging.set_verbosity(tf.logging.WARN)
        #模型参数
        lr = self.config.lr
        n_timesteps = self.config.n_timesteps
        n_dimension = self.config.n_dimension
        n_hidden = self.config.n_hidden
        tf.reset_default_graph()
        # 加载模型
        if model_type == self.config.Fed_LSTM or model_type == self.config.LSTM:
            client_model = LSTMModel(config=self.config, seed=random_seed)
        else:
            print('输入模型类型不存在，进程结束')
            return
            # 创建服务器
        server = Server(self.config, client_model)
        # 创建客户端
        # 每一个工厂一个客户端
        clients = setup_clients(self.config, model_type, client_model)
        client_ids, client_groups, client_num_samples = server.get_clients_info(clients)
        print('Clients in Total: %d' % len(clients))
        # 初始化状态
        print('--- Random Initialization ---')
        # 用来保存状态
        stat_writer_fn = get_stat_writer_function(client_ids, client_groups, client_num_samples, self.config)
        sys_writer_fn = get_sys_writer_function(self.config)
        print_stats(0, server, clients, client_num_samples, stat_writer_fn)
        num_rounds = self.config.num_rounds
        eval_every = self.config.eval_every
        clients_per_round = self.config.clients_per_round
        num_epochs = self.config.num_epochs
        batch_size = self.config.batch_size
        # 模拟训练
        for i in range(num_rounds):
            print('--- Round %d of %d: Training %d Clients ---' % (i + 1, num_rounds, clients_per_round))

            # 当前轮选择的客户端
            server.select_clients(i, online(clients), num_clients=clients_per_round)
            c_ids, c_groups, c_num_samples = server.get_clients_info(server.selected_clients)

            # Simulate server model training on selected clients' data
            sys_metrics = server.train_model(num_epochs=num_epochs, batch_size=batch_size,
                                             minibatch=None)
            sys_writer_fn(i + 1, c_ids, sys_metrics, c_groups, c_num_samples)

            # 更新server模型
            server.update_model()

            # Test model
            if (i + 1) % eval_every == 0 or (i + 1) == num_rounds:
                print_stats(i + 1, server, clients, client_num_samples, stat_writer_fn)
        # Save server model
        ckpt_path = os.path.join('checkpoints', str(int(time.time())))
        if not os.path.exists(ckpt_path):
            os.makedirs(ckpt_path)
        save_path = server.save_model(os.path.join(ckpt_path, 'lstm.ckpt'))
        print('Model saved in path: %s' % save_path)

        # Close models
        server.close_model()


# 这里可以对客户端的状态进行设置，模拟各种不在线情况
def online(clients):
    """假设所有用户都在线"""
    return clients


def create_clients(users, groups, train_data, test_data, model):
    if len(groups) == 0:
        groups = [[] for _ in users]
    clients = [Client(u, g, train_data[u], test_data[u], model) for u, g in zip(users, groups)]
    return clients


def setup_clients(config, model_type=None, model=None):
    """基于给定的训练数据文件夹和测试数据文件夹

    Return:
        all_clients: list of Client objects.
    """
    if model_type == config.Fed_LSTM :
        train_data_dir = config.train_data_dir
        test_data_dir = config.test_data_dir
    else:
        train_data_dir = config.train_data_dir
        test_data_dir = config.test_data_dir
    users, groups, train_data, test_data = read_data(train_data_dir, test_data_dir)

    clients = create_clients(users, groups, train_data, test_data, model)

    return clients


def get_stat_writer_function(ids, groups, num_samples, config):
    def writer_fn(num_round, metrics, partition):
        metrics_writer.print_metrics(
            num_round, ids, metrics, groups, num_samples, partition, config.metrics_dir,
            '{}_{}'.format(config.metrics_name, 'stat'))

    return writer_fn


def get_sys_writer_function(config):
    def writer_fn(num_round, ids, metrics, groups, num_samples):
        metrics_writer.print_metrics(
            num_round, ids, metrics, groups, num_samples, 'systrain', config.metrics_dir,
            '{}_{}'.format(config.metrics_name, 'sys'))

    return writer_fn


def print_stats(
        num_round, server, clients, num_samples, writer, use_val_set=False):
    # 每一个客户端的指标
    train_stat_metrics = server.test_model(clients, set_to_use='train')  
    print_metrics(train_stat_metrics, num_samples, prefix='train_')
    writer(num_round, train_stat_metrics, 'train')

    eval_set = 'test' if not use_val_set else 'val'
    test_stat_metrics = server.test_model(clients, set_to_use=eval_set)
    print_metrics(test_stat_metrics, num_samples, prefix='{}_'.format(eval_set))
    writer(num_round, test_stat_metrics, eval_set)


def print_metrics(metrics, weights, prefix=''):
    """Prints weighted averages of the given metrics.

    Args:
        metrics: dict with client ids as keys. Each entry is a dict
            with the metrics of that client.
        weights: dict with client ids as keys. Each entry is the weight
            for that client.
    """
    ordered_weights = [weights[c] for c in sorted(weights)]
    metric_names = metrics_writer.get_metrics_names(metrics)
    to_ret = None
