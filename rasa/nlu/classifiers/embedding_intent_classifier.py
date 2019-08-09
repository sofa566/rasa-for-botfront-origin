import io
import logging
import numpy as np
import os
import pickle
import typing
from typing import Any, Dict, List, Optional, Text, Tuple

from rasa.nlu.classifiers import INTENT_RANKING_LENGTH
from rasa.nlu.components import Component
from rasa.utils import train_utils

import tensorflow as tf

# avoid warning println on contrib import - remove for tf 2
tf.contrib._warning = None

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from rasa.nlu.config import RasaNLUModelConfig
    from rasa.nlu.training_data import TrainingData
    from rasa.nlu.model import Metadata
    from rasa.nlu.training_data import Message


class EmbeddingIntentClassifier(Component):
    """Intent classifier using supervised embeddings.

    The embedding intent classifier embeds user inputs
    and intent labels into the same space.
    Supervised embeddings are trained by maximizing similarity between them.
    It also provides rankings of the labels that did not "win".

    The embedding intent classifier needs to be preceded by
    a featurizer in the pipeline.
    This featurizer creates the features used for the embeddings.
    It is recommended to use ``CountVectorsFeaturizer`` that
    can be optionally preceded by ``SpacyNLP`` and ``SpacyTokenizer``.

    Based on the starspace idea from: https://arxiv.org/abs/1709.03856.
    However, in this implementation the `mu` parameter is treated differently
    and additional hidden layers are added together with dropout.
    """

    provides = ["intent", "intent_ranking"]

    requires = ["text_features"]

    # default properties (DOC MARKER - don't remove)
    defaults = {
        # nn architecture
        # sizes of hidden layers before the embedding layer for input words
        # the number of hidden layers is thus equal to the length of this list
        "hidden_layers_sizes_a": [256, 128],
        # sizes of hidden layers before the embedding layer for intent labels
        # the number of hidden layers is thus equal to the length of this list
        "hidden_layers_sizes_b": [],
        # training parameters
        # initial and final batch sizes - batch size will be
        # linearly increased for each epoch
        "batch_size": [64, 256],
        # how to create batches
        "batch_strategy": "balanced",  # string 'sequence' or 'balanced'
        # number of epochs
        "epochs": 300,
        # set random seed to any int to get reproducible results
        "random_seed": None,
        # embedding parameters
        # dimension size of embedding vectors
        "embed_dim": 20,
        # the type of the similarity
        "num_neg": 20,
        # flag if minimize only maximum similarity over incorrect actions
        "similarity_type": "auto",  # string 'auto' or 'cosine' or 'inner'
        # the type of the loss function
        "loss_type": "softmax",  # string 'softmax' or 'margin'
        # how similar the algorithm should try
        # to make embedding vectors for correct intent labels
        "mu_pos": 0.8,  # should be 0.0 < ... < 1.0 for 'cosine'
        # maximum negative similarity for incorrect intent labels
        "mu_neg": -0.4,  # should be -1.0 < ... < 1.0 for 'cosine'
        # flag: if true, only minimize the maximum similarity for
        # incorrect intent labels
        "use_max_sim_neg": True,
        # scale loss inverse proportionally to confidence of correct prediction
        "scale_loss": True,
        # regularization parameters
        # the scale of L2 regularization
        "C2": 0.002,
        # the scale of how critical the algorithm should be of minimizing the
        # maximum similarity between embeddings of different intent labels
        "C_emb": 0.8,
        # dropout rate for rnn
        "droprate": 0.2,
        # flag: if true, the algorithm will split the intent labels into tokens
        #       and use bag-of-words representations for them
        "intent_tokenization_flag": False,
        # delimiter string to split the intent labels
        "intent_split_symbol": "_",
        # visualization of accuracy
        # how often to calculate training accuracy
        "evaluate_every_num_epochs": 20,  # small values may hurt performance
        # how many examples to use for calculation of training accuracy
        "evaluate_on_num_examples": 0,  # large values may hurt performance
    }
    # end default properties (DOC MARKER - don't remove)

    def __init__(
        self,
        component_config: Optional[Dict[Text, Any]] = None,
        inv_intent_dict: Optional[Dict[int, Text]] = None,
        session: Optional["tf.Session"] = None,
        graph: Optional["tf.Graph"] = None,
        message_placeholder: Optional["tf.Tensor"] = None,
        intent_placeholder: Optional["tf.Tensor"] = None,
        similarity_all: Optional["tf.Tensor"] = None,
        pred_confidence: Optional["tf.Tensor"] = None,
        similarity: Optional["tf.Tensor"] = None,
        message_embed: Optional["tf.Tensor"] = None,
        intent_embed: Optional["tf.Tensor"] = None,
        all_intents_embed: Optional["tf.Tensor"] = None,
    ) -> None:
        """Declare instant variables with default values"""

        super(EmbeddingIntentClassifier, self).__init__(component_config)

        self._load_params()

        # transform numbers to intents
        self.inv_intent_dict = inv_intent_dict
        # encode all intents with numbers
        self._encoded_all_intents = None

        # tf related instances
        self.session = session
        self.graph = graph
        self.a_in = message_placeholder
        self.b_in = intent_placeholder
        self.sim_all = similarity_all
        self.pred_confidence = pred_confidence
        self.sim = similarity

        # persisted embeddings
        self.message_embed = message_embed
        self.intent_embed = intent_embed
        self.all_intents_embed = all_intents_embed

        # internal tf instances
        self._iterator = None
        self._train_op = None
        self._is_training = None

    # init helpers
    def _load_nn_architecture_params(self, config: Dict[Text, Any]) -> None:
        self.hidden_layer_sizes = {
            "a": config["hidden_layers_sizes_a"],
            "b": config["hidden_layers_sizes_b"],
        }

        self.batch_size = config["batch_size"]
        self.batch_strategy = config["batch_strategy"]

        self.epochs = config["epochs"]

        self.random_seed = self.component_config["random_seed"]

    def _load_embedding_params(self, config: Dict[Text, Any]) -> None:
        self.embed_dim = config["embed_dim"]
        self.num_neg = config["num_neg"]

        self.similarity_type = config["similarity_type"]
        self.loss_type = config["loss_type"]
        if self.similarity_type == "auto":
            if self.loss_type == "softmax":
                self.similarity_type = "inner"
            elif self.loss_type == "margin":
                self.similarity_type = "cosine"

        self.mu_pos = config["mu_pos"]
        self.mu_neg = config["mu_neg"]
        self.use_max_sim_neg = config["use_max_sim_neg"]

        self.scale_loss = config["scale_loss"]

    def _load_regularization_params(self, config: Dict[Text, Any]) -> None:
        self.C2 = config["C2"]
        self.C_emb = config["C_emb"]
        self.droprate = config["droprate"]

    def _load_flag_if_tokenize_intents(self, config: Dict[Text, Any]) -> None:
        self.intent_tokenization_flag = config["intent_tokenization_flag"]
        self.intent_split_symbol = config["intent_split_symbol"]
        if self.intent_tokenization_flag and not self.intent_split_symbol:
            logger.warning(
                "intent_split_symbol was not specified, "
                "so intent tokenization will be ignored"
            )
            self.intent_tokenization_flag = False

    def _load_visual_params(self, config: Dict[Text, Any]) -> None:
        self.evaluate_every_num_epochs = config["evaluate_every_num_epochs"]
        if self.evaluate_every_num_epochs < 1:
            self.evaluate_every_num_epochs = self.epochs
        self.evaluate_on_num_examples = config["evaluate_on_num_examples"]

    def _load_params(self) -> None:

        self._load_nn_architecture_params(self.component_config)
        self._load_embedding_params(self.component_config)
        self._load_regularization_params(self.component_config)
        self._load_flag_if_tokenize_intents(self.component_config)
        self._load_visual_params(self.component_config)

    # package safety checks
    @classmethod
    def required_packages(cls) -> List[Text]:
        return ["tensorflow"]

    # training data helpers:
    @staticmethod
    def _create_intent_dict(training_data: "TrainingData") -> Dict[Text, int]:
        """Create intent dictionary"""

        distinct_intents = set(
            [example.get("intent") for example in training_data.intent_examples]
        )
        return {intent: idx for idx, intent in enumerate(sorted(distinct_intents))}

    @staticmethod
    def _create_intent_token_dict(
        intents: List[Text], intent_split_symbol: Text
    ) -> Dict[Text, int]:
        """Create intent token dictionary"""

        distinct_tokens = set(
            [token for intent in intents for token in intent.split(intent_split_symbol)]
        )
        return {token: idx for idx, token in enumerate(sorted(distinct_tokens))}

    def _create_encoded_intents(self, intent_dict: Dict[Text, int]) -> np.ndarray:
        """Create matrix with intents encoded in rows as bag of words.

        If intent_tokenization_flag is off, returns identity matrix.
        """

        if self.intent_tokenization_flag:
            intent_token_dict = self._create_intent_token_dict(
                list(intent_dict.keys()), self.intent_split_symbol
            )

            encoded_all_intents = np.zeros((len(intent_dict), len(intent_token_dict)))
            for key, idx in intent_dict.items():
                for t in key.split(self.intent_split_symbol):
                    encoded_all_intents[idx, intent_token_dict[t]] = 1

            return encoded_all_intents
        else:
            return np.eye(len(intent_dict))

    # noinspection PyPep8Naming
    def _create_all_Y(self, size: int) -> np.ndarray:
        """Stack encoded_all_intents on top of each other

        to create candidates for training examples and
        to calculate training accuracy
        """

        return np.stack([self._encoded_all_intents] * size)

    # noinspection PyPep8Naming
    def _create_session_data(
        self, training_data: "TrainingData", intent_dict: Dict[Text, int]
    ) -> "train_utils.SessionData":
        """Prepare data for training"""

        X = np.stack([e.get("text_features") for e in training_data.intent_examples])

        labels = np.array(
            [intent_dict[e.get("intent")] for e in training_data.intent_examples]
        )

        Y = np.stack([self._encoded_all_intents[intent_idx] for intent_idx in labels])

        return train_utils.SessionData(X=X, Y=Y, labels=labels)

    # tf helpers:
    def _create_tf_embed_fnn(
        self, x_in: "tf.Tensor", layer_sizes: List[int], name: Text
    ) -> "tf.Tensor":
        """Create nn with hidden layers and name"""

        x = train_utils.create_tf_fnn(
            x_in,
            layer_sizes,
            self.droprate,
            self.C2,
            self._is_training,
            layer_name_suffix=name,
        )
        return train_utils.create_tf_embed(
            x, self.embed_dim, self.C2, self.similarity_type, layer_name_suffix=name
        )

    def _build_tf_train_graph(self) -> Tuple["tf.Tensor", "tf.Tensor"]:
        self.a_in, self.b_in = self._iterator.get_next()

        all_intents = tf.constant(
            self._encoded_all_intents, dtype=tf.float32, name="all_intents"
        )

        self.message_embed = self._create_tf_embed_fnn(
            self.a_in, self.hidden_layer_sizes["a"], name="a"
        )

        self.intent_embed = self._create_tf_embed_fnn(
            self.b_in, self.hidden_layer_sizes["b"], name="b"
        )
        self.all_intents_embed = self._create_tf_embed_fnn(
            all_intents, self.hidden_layer_sizes["b"], name="b"
        )

        return train_utils.calculate_loss_acc(
            self.message_embed,
            self.intent_embed,
            self.b_in,
            self.all_intents_embed,
            all_intents,
            self.num_neg,
            None,
            self.loss_type,
            self.mu_pos,
            self.mu_neg,
            self.use_max_sim_neg,
            self.C_emb,
            self.scale_loss,
        )

    def _build_tf_pred_graph(self, session_data: "train_utils.SessionData") -> "tf.Tensor":
        self.a_in = tf.placeholder(
            tf.float32, (None, session_data.X.shape[-1]), name="a"
        )
        self.b_in = tf.placeholder(
            tf.float32, (None, None, session_data.Y.shape[-1]), name="b"
        )

        self.message_embed = self._create_tf_embed_fnn(
            self.a_in, self.hidden_layer_sizes["a"], name="a"
        )

        self.sim_all = train_utils.tf_raw_sim(
            self.message_embed[:, tf.newaxis, :],
            self.all_intents_embed[tf.newaxis, :, :],
            None,
        )

        self.intent_embed = self._create_tf_embed_fnn(
            self.b_in, self.hidden_layer_sizes["b"], name="b"
        )

        self.sim = train_utils.tf_raw_sim(
            self.message_embed[:, tf.newaxis, :], self.intent_embed, None
        )

        return train_utils.confidence_from_sim(self.sim_all, self.similarity_type)

    def train(
        self,
        training_data: "TrainingData",
        cfg: Optional["RasaNLUModelConfig"] = None,
        **kwargs: Any
    ) -> None:
        """Train the embedding intent classifier on a data set."""

        logger.debug("Started training embedding classifier.")

        # set numpy random seed
        np.random.seed(self.random_seed)

        intent_dict = self._create_intent_dict(training_data)
        if len(intent_dict) < 2:
            logger.error(
                "Can not train an intent classifier. "
                "Need at least 2 different classes. "
                "Skipping training of intent classifier."
            )
            return

        self.inv_intent_dict = {v: k for k, v in intent_dict.items()}
        self._encoded_all_intents = self._create_encoded_intents(intent_dict)

        # check if number of negatives is less than number of intents
        logger.debug(
            "Check if num_neg {} is smaller than "
            "number of intents {}, "
            "else set num_neg to the number of intents - 1"
            "".format(self.num_neg, self._encoded_all_intents.shape[0])
        )
        # noinspection PyAttributeOutsideInit
        self.num_neg = min(self.num_neg, self._encoded_all_intents.shape[0] - 1)

        session_data = self._create_session_data(training_data, intent_dict)

        if self.evaluate_on_num_examples:
            session_data, eval_session_data = train_utils.train_val_split(
                session_data, self.evaluate_on_num_examples, self.random_seed
            )
        else:
            eval_session_data = None

        self.graph = tf.Graph()
        with self.graph.as_default():
            # set random seed
            tf.set_random_seed(self.random_seed)

            # allows increasing batch size
            batch_size_in = tf.placeholder(tf.int64)

            (
                self._iterator,
                train_init_op,
                eval_init_op,
            ) = train_utils.create_iterator_init_datasets(
                session_data, eval_session_data, batch_size_in, self.batch_strategy
            )

            self._is_training = tf.placeholder_with_default(False, shape=())

            loss, acc = self._build_tf_train_graph()

            # define which optimizer to use
            self._train_op = tf.train.AdamOptimizer().minimize(loss)

            # train tensorflow graph
            self.session = tf.Session()
            train_utils.train_tf_dataset(
                train_init_op,
                eval_init_op,
                batch_size_in,
                loss,
                acc,
                self._train_op,
                self.session,
                self._is_training,
                self.epochs,
                self.batch_size,
                self.evaluate_on_num_examples,
                self.evaluate_every_num_epochs,
            )

            # rebuild the graph for prediction
            self.pred_confidence = self._build_tf_pred_graph(session_data)

    # process helpers
    # noinspection PyPep8Naming
    def _calculate_message_sim(self, X: np.ndarray) -> Tuple[np.ndarray, List[float]]:
        """Calculate message similarities"""

        message_sim = self.session.run(self.pred_confidence, feed_dict={self.a_in: X})

        message_sim = message_sim.flatten()  # sim is a matrix

        intent_ids = message_sim.argsort()[::-1]
        message_sim[::-1].sort()

        # transform sim to python list for JSON serializing
        return intent_ids, message_sim.tolist()

    def process(self, message: "Message", **kwargs: Any) -> None:
        """Return the most likely intent and its similarity to the input."""

        intent = {"name": None, "confidence": 0.0}
        intent_ranking = []

        if self.session is None:
            logger.error(
                "There is no trained tf.session: "
                "component is either not trained or "
                "didn't receive enough training data"
            )

        else:
            # get features (bag of words) for a message
            # noinspection PyPep8Naming
            X = message.get("text_features").reshape(1, -1)

            # load tf graph and session
            intent_ids, message_sim = self._calculate_message_sim(X)

            # if X contains all zeros do not predict some label
            if X.any() and intent_ids.size > 0:
                intent = {
                    "name": self.inv_intent_dict[intent_ids[0]],
                    "confidence": message_sim[0],
                }

                ranking = list(zip(list(intent_ids), message_sim))
                ranking = ranking[:INTENT_RANKING_LENGTH]
                intent_ranking = [
                    {"name": self.inv_intent_dict[intent_idx], "confidence": score}
                    for intent_idx, score in ranking
                ]

        message.set("intent", intent, add_to_output=True)
        message.set("intent_ranking", intent_ranking, add_to_output=True)

    def persist(self, file_name: Text, model_dir: Text) -> Dict[Text, Any]:
        """Persist this model into the passed directory.

        Return the metadata necessary to load the model again.
        """

        if self.session is None:
            return {"file": None}

        checkpoint = os.path.join(model_dir, file_name + ".ckpt")

        try:
            os.makedirs(os.path.dirname(checkpoint))
        except OSError as e:
            # be happy if someone already created the path
            import errno

            if e.errno != errno.EEXIST:
                raise
        with self.graph.as_default():
            train_utils.persist_tensor("message_placeholder", self.a_in, self.graph)
            train_utils.persist_tensor("intent_placeholder", self.b_in, self.graph)

            train_utils.persist_tensor("similarity_all", self.sim_all, self.graph)
            train_utils.persist_tensor("pred_confidence", self.pred_confidence, self.graph)
            train_utils.persist_tensor("similarity", self.sim, self.graph)

            train_utils.persist_tensor("message_embed", self.message_embed, self.graph)
            train_utils.persist_tensor("intent_embed", self.intent_embed, self.graph)

            saver = tf.train.Saver()
            saver.save(self.session, checkpoint)

        with io.open(
            os.path.join(model_dir, file_name + "_inv_intent_dict.pkl"), "wb"
        ) as f:
            pickle.dump(self.inv_intent_dict, f)

        return {"file": file_name}

    @classmethod
    def load(
        cls,
        meta: Dict[Text, Any],
        model_dir: Text = None,
        model_metadata: "Metadata" = None,
        cached_component: Optional["EmbeddingIntentClassifier"] = None,
        **kwargs: Any
    ) -> "EmbeddingIntentClassifier":

        if model_dir and meta.get("file"):
            file_name = meta.get("file")
            checkpoint = os.path.join(model_dir, file_name + ".ckpt")
            graph = tf.Graph()
            with graph.as_default():
                sess = tf.Session()
                saver = tf.train.import_meta_graph(checkpoint + ".meta")

                saver.restore(sess, checkpoint)

                a_in = train_utils.load_tensor("message_placeholder")
                b_in = train_utils.load_tensor("intent_placeholder")

                sim_all = train_utils.load_tensor("similarity_all")
                pred_confidence = train_utils.load_tensor("pred_confidence")
                sim = train_utils.load_tensor("similarity")

                message_embed = train_utils.load_tensor("message_embed")
                intent_embed = train_utils.load_tensor("intent_embed")
                all_intents_embed = train_utils.load_tensor("all_intents_embed")

            with io.open(
                os.path.join(model_dir, file_name + "_inv_intent_dict.pkl"), "rb"
            ) as f:
                inv_intent_dict = pickle.load(f)

            return cls(
                component_config=meta,
                inv_intent_dict=inv_intent_dict,
                session=sess,
                graph=graph,
                message_placeholder=a_in,
                intent_placeholder=b_in,
                similarity_all=sim_all,
                pred_confidence=pred_confidence,
                similarity=sim,
                message_embed=message_embed,
                intent_embed=intent_embed,
                all_intents_embed=all_intents_embed,
            )

        else:
            logger.warning(
                "Failed to load nlu model. Maybe path {} "
                "doesn't exist"
                "".format(os.path.abspath(model_dir))
            )
            return cls(component_config=meta)
