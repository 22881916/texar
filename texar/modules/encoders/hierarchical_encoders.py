# Copyright 2018 The Texar Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Various encoders that encode data with hierarchical structure.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections

import tensorflow as tf
from tensorflow.contrib.rnn import LSTMStateTuple

from texar.modules.encoders.encoder_base import EncoderBase
from texar.utils import utils

# pylint: disable=invalid-name, too-many-arguments, too-many-locals

__all__ = [
    "HierarchicalRNNEncoder"
]

class HierarchicalRNNEncoder(EncoderBase):
    """A hierarchical encoder that stacks basic RNN encoders into two layers.
    Can be used to encode long, structured sequences, e.g. paragraphs, dialog
    history, etc.

    Args:
        encoder_major (optional): An instance of subclass of
            :class:`~texar.modules.RNNEncoderBase`
            The high-level encoder taking final
            states from low-level encoder as its
            inputs. If not specified, an encoder
            is created as specified in
            :attr:`hparams["encoder_major"]`.
        encoder_minor (optional): An instance of subclass of
            :class:`~texar.modules.RNNEncoderBase`
            The low-level encoder. If not
            specified, an encoder is created as specified
            in :attr:`hparams["encoder_minor"]`.
        hparams (dict or HParams, optional): Hyperparameters. Missing
            hyperparamerter will be set to default values. See
            :meth:`default_hparams` for the hyperparameter sturcture and
            default values.

    See :meth:`_build` for the inputs and outputs of the encoder.

    .. document private functions
    .. automethod:: _build
    """

    def __init__(self, encoder_major=None, encoder_minor=None,
                 hparams=None):
        EncoderBase.__init__(self, hparams)

        encoder_major_hparams = utils.get_instance_kwargs(
            None, self._hparams.encoder_major_hparams)
        encoder_minor_hparams = utils.get_instance_kwargs(
            None, self._hparams.encoder_minor_hparams)

        if encoder_major is not None:
            self._encoder_major = encoder_major
        else:
            with tf.variable_scope(self.variable_scope.name):
                with tf.variable_scope('encoder_major'):
                    self._encoder_major = utils.check_or_get_instance(
                        self._hparams.encoder_major_type,
                        encoder_major_hparams,
                        ['texar.modules.encoders', 'texar.custom'])

        if encoder_minor is not None:
            self._encoder_minor = encoder_minor
        elif self._hparams.config_share:
            with tf.variable_scope(self.variable_scope.name):
                with tf.variable_scope('encoder_minor'):
                    self._encoder_minor = utils.check_or_get_instance(
                        self._hparams.encoder_major_type,
                        encoder_major_hparams,
                        ['texar.modules.encoders', 'texar.custom'])
        else:
            with tf.variable_scope(self.variable_scope.name):
                with tf.variable_scope('encoder_minor'):
                    self._encoder_minor = utils.check_or_get_instance(
                        self._hparams.encoder_minor_type,
                        encoder_minor_hparams,
                        ['texar.modules.encoders', 'texar.custom'])

    @staticmethod
    def default_hparams():
        """Returns a dictionary of hyperparameters with default values.

        .. role:: python(code)
           :language: python

        .. code-block:: python

            {
                "encoder_major_type": "UnidirectionalRNNEncoder",
                "encoder_major_hparams": {},
                "encoder_minor_type": "UnidirectionalRNNEncoder",
                "encoder_minor_hparams": {},
                "config_share": False,
                "name": "hierarchical_encoder_wrapper"
            }

        Here:

        "encoder_major_type" : str or class or instance
            The high-level encoder. Can be a RNN encoder class, its name or
            module path, or a class instance.
            Ignored if `encoder_major` is given to the encoder constructor.

        "encoder_major_hparams" : dict
            The hyperparameters for the high-level encoder. The high-level
            encoder is created with
            :python:`encoder_class(hparams=encoder_major_hparams)`.
            Ignored if `encoder_major` is given to the encoder constructor,
            or if "encoder_major_type" is an encoder instance.

        "encoder_minor_type" : str or class or instance
            The low-level encoder. Can be a RNN encoder class, its name or
            module path, or a class instance.
            Ignored if `encoder_minor` is given to the encoder constructor,
            or if "config_share" is True.

        "encoder_minor_hparams" : dict
            The hyperparameters for the low-level encoder. The high-level
            encoder is created with
            :python:`encoder_class(hparams=encoder_minor_hparams)`.
            Ignored if `encoder_minor` is given to the encoder constructor,
            or if "config_share" is True,
            or if "encoder_minor_type" is an encoder instance.

        "config_share":
            Whether to use encoder_major's hyperparameters
            to construct encoder_minor.

        "name":
            Name of the encoder.
        """
        hparams = {
            "name": "hierarchical_encoder",
            "encoder_major_type": "UnidirectionalRNNEncoder",
            "encoder_major_hparams": {},
            "encoder_minor_type": "UnidirectionalRNNEncoder",
            "encoder_minor_hparams": {},
            "config_share": False,
            "@no_typecheck": [
                'encoder_major_hparams',
                'encoder_minor_hparams'
            ]
        }
        hparams.update(EncoderBase.default_hparams())
        return hparams

    def _build(self,
               inputs,
               order='btu',
               medium=None,
               sequence_length_major=None,
               sequence_length_minor=None,
               **kwargs):
        """Encodes the inputs.

        Args:
            inputs: A 4-D tensor of shape `[B, T, U, dim]`, where

                - B: batch_size
                - T: the major seq len (high-level length)
                - U: the minor seq len (low-level length)
                - dim: embedding dimension

                The order of first three dimensions can be changed
                according to the argument :attr:`time_major` of the two
                encoders.

            order: a 3-char string containing 'b', 't', and 'u',
                that specifies the order of inputs dimension.
                Following four can be accepted:

                    - 'btu': set time_major=False for both. (default)
                    - 'utb': set time_major=True for both.
                    - 'tbu': set time_major=True for major encoder only.
                    - 'ubt': set time_major=True for minor encoder only.

            medium (optional): A list of callables that subsequently process the
                final states of minor encoder and obtain the inputs
                for the major encoder.

                If not specified, :meth:`flatten` is used for processing
                the minor's final states.

            sequence_length_minor (optional): The `sequence_length` kwarg sent
                to minor encoder. It can be either a 1-D tensor or 2-D tensor, 
                with BxT units following correct order.

            sequence_length_major (optional): The `sequence_length` kwarg sent
                to major encoder.

            **kwargs: Other keyword arguments for the major and minor encoders,
                such as `initial_state` and so on, except `time_major`, which 
                will be automatically derived from `order` args.

                By default, arguments will be sent to both major and minor
                encoders. To specify the encoder that arguments sent to, add
                '_minor'/'_major' as its suffix.

                `initial_state_minor` must be provided with B,T dims flatten
                into one dim of length BxT.

        Returns:
            `(outputs, final_state)` by the major encoder.
        """

        def _kwargs_split(kwargs):
            kwargs_minor, kwargs_major = {}, {}
            for k, v in kwargs.items():
                if len(k) >= 6 and k[-6:] == ['_minor']:
                    kwargs_minor[k[:-6]] = v
                if len(k) >= 6 and k[-6:] == ['_major']:
                    kwargs_major[k[:-6]] = v

            kwargs_minor['sequence_length'] = sequence_length_minor
            kwargs_major['sequence_length'] = sequence_length_major

            return kwargs_minor, kwargs_major

        kwargs_minor, kwargs_major = _kwargs_split(kwargs)

        shape = tf.shape(inputs)[:3]

        expand, shape = self._get_flatten_order(
            order, kwargs_major, kwargs_minor, tf.shape(inputs))

        inputs = tf.reshape(inputs, shape + [inputs.shape[3]])

        _, states_minor = self._encoder_minor(inputs, **kwargs_minor)

        self.states_minor_before_medium = states_minor

        if medium is None:
            states_minor = self.flatten(states_minor)
        else:
            if not isinstance(medium, collections.Sequence):
                medium = [medium]
            for fn in medium:
                if isinstance(fn, str) and fn == 'flatten':
                    states_minor = self.flatten(states_minor)
                else:
                    states_minor = fn(states_minor)

        self.states_minor_after_medium = states_minor

        states_minor = tf.reshape(
            states_minor, tf.concat([expand, tf.shape(states_minor)[1:]], 0))

        outputs_major, states_major = self._encoder_major(states_minor,
                                                          **kwargs_major)

        # Add trainable variables of `self._cell` which may be constructed
        # externally
        if not self._built:
            self._add_trainable_variable(
                self._encoder_minor.trainable_variables)
            self._add_trainable_variable(
                self._encoder_major.trainable_variables)
            self._built = True

        return outputs_major, states_major

    @staticmethod
    def _get_flatten_order(order, kwargs_minor, kwargs_major, shape):
        if order == 'btu':
            kwargs_minor.setdefault('time_major', False)
            kwargs_major.setdefault('time_major', False)
            expand = shape[0:2]
            shape = [shape[0] * shape[1], shape[2]]
        elif order == 'utb':
            kwargs_minor.setdefault('time_major', True)
            kwargs_major.setdefault('time_major', True)
            expand = shape[1:3]
            shape = [shape[0], shape[1] * shape[2]]
        elif order == 'tbu':
            kwargs_minor.setdefault('time_major', False)
            kwargs_major.setdefault('time_major', True)
            expand = shape[0:2]
            shape = [shape[0] * shape[1], shape[2]]
        elif order == 'ubt':
            kwargs_minor.setdefault('time_major', True)
            kwargs_major.setdefault('time_major', False)
            expand = shape[1:3]
            shape = [shape[0], shape[1] * shape[2]]

        return expand, shape

    @staticmethod
    def flatten(x):
        """Flattens a cell state by concatenating a sequence of cell
        states along the last dimension. If the cell states are
        :tf_main:`LSTMStateTuple <contrib/rnn/LSTMStateTuple>`, only the
        hidden `LSTMStateTuple.h` is used.

        This process is used by default if :attr:`medium` is not provided
        to :meth:`_build`.
        """
        if isinstance(x, LSTMStateTuple):
            return x.h
        if isinstance(x, collections.Sequence):
            return tf.concat(
                [HierarchicalRNNEncoder.flatten(v) for v in x], -1)
        else:
            return x

    @property
    def encoder_major(self):
        """The high-level encoder.
        """
        return self._encoder_major

    @property
    def encoder_minor(self):
        """The low-level encoder.
        """
        return self._encoder_minor
