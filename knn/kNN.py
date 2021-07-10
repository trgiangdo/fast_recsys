import progressbar

import numpy as np

from utils import timer
from .similarities import _cosine, _pcc, _cosine_genome, _pcc_genome
from .knn_helper import _predict


class kNN:
    """Reimplementation of kNN argorithm.

    Args:
        k (int): Number of neibors use in prediction
        min_k (int): The minimum number of neighbors to take into account for aggregation. If there are not enough neighbors, the neighbor aggregation is set to zero
        uuCF (boolean, optional): True if using user-based CF, False if using item-based CF. Defaults to `False`.
        verbose (boolean): Show predicting progress. Defaults to `False`.
        awareness_constrain (boolean): If `True`, the model must aware of all users and items in the test set, which means that these users and items are in the train set as well. This constrain helps speed up the predicting process (up to 1.5 times) but if a user of an item is unknown, kNN will fail to give prediction. Defaults to `False`.
    """
    def __init__(self, k, min_k=1, uuCF=False, verbose=False, awareness_constrain=False):
        self.k = k
        self.min_k = min_k

        self.uuCF = uuCF

        self.verbose = verbose
        self.awareness_constrain = awareness_constrain

    def fit(self, train_data, similarity_measure="cosine", genome=None, similarity_matrix=None):
        """Fit data (utility matrix) into the predicting model.

        Args:
            data (ndarray): Training data.
            similarity_measure (str, optional): Similarity measure function. Defaults to "cosine".
            genome (ndarray): Movie genome scores from MovieLens 20M. Defaults to "None".
            similarity_matrix (ndarray): Pre-calculate similarity matrix.  Defaults to "None".
        """
        self.X = train_data.copy()

        if not self.uuCF:
            self.X[:, [0, 1]] = self.X[:, [1, 0]]     # Swap user_id column to movie_id column

        self.global_mean = np.mean(self.X[:, 2])

        self.x_list = np.unique(self.X[:, 0])       # For uuCF, x -> user
        self.y_list = np.unique(self.X[:, 1])       # For uuCF, y -> item

        self.n_x = len(self.x_list)
        self.n_y = len(self.y_list)

        self.x_rated = [[] for _ in range(self.n_y)]        # List where element `i` is ndarray of `(x, rating)` where `x` is all x that rated y, and the ratings.
        self.y_ratedby = [[] for _ in range(self.n_x)]      # List where element `i` is ndarray of `(y, rating)` where `y` is all y that rated by x, and the ratings.
        print("Listing all users rated each item (or vice versa if iiCF) ...")
        for xid, yid, r in self.X:
            self.x_rated[int(yid)].append([xid, r])
            self.y_ratedby[int(xid)].append([yid, r])

        for yid in range(self.n_y):
            self.x_rated[yid] = np.array(self.x_rated[yid])
        for xid in range(self.n_x):
            self.y_ratedby[xid] = np.array(self.y_ratedby[xid])

        if similarity_matrix is None:
            print('Computing similarity matrix ...')

            self.__supported_sim_func = ["cosine", "pearson"]
            assert similarity_measure in self.__supported_sim_func, f"Similarity measure function should be one of {self.__supported_sim_func}"
            self.__similarity_measure = similarity_measure

            if self.__similarity_measure == "cosine":
                if genome is not None:
                    self.S = _cosine_genome(genome)
                else:
                    self.S = _cosine(self.n_x, self.x_rated)
            elif self.__similarity_measure == "pearson":
                if genome is not None:
                    self.S = _pcc_genome(genome)
                else:
                    self.S = _pcc(self.n_x, self.x_rated)
        else:
            self.S = similarity_matrix

    @timer("Time for predicting: ")
    def predict(self, test_set):
        """Returns estimated ratings of several given user/item pairs.
        Args:
            test_set (adarray): storing all user/item pairs we want to predict the ratings.
        Returns:
            predictions (ndarray): Storing all predictions of the given user/item pairs.
        """
        if not self.uuCF:
            test_set[:, [0, 1]] = test_set[:, [1, 0]]     # Swap user_id column to movie_id column

        self.predictions = []
        self.ground_truth = test_set[:, 2]
        n_pairs = test_set.shape[0]

        print(f"Predicting {n_pairs} pairs of user-item ...")

        if self.verbose:
            bar = progressbar.ProgressBar(maxval=n_pairs, widgets=[progressbar.Bar(), ' ', progressbar.Percentage()])
            bar.start()
            for pair in range(n_pairs):
                self.predictions.append(self.predict_pair(test_set[pair, 0].astype(int), test_set[pair, 1].astype(int)))
                bar.update(pair + 1)
            bar.finish()
        else:
            for pair in range(n_pairs):
                self.predictions.append(self.predict_pair(test_set[pair, 0].astype(int), test_set[pair, 1].astype(int)))

        self.predictions = np.array(self.predictions)
        return self.predictions

    def predict_pair(self, x_id, y_id):
        """Predict the rating of user u for item i

        Args:
            x_id (int): index of x (For uuCF, x -> user)
            y_id (int): index of y (For uuCF, y -> item)

        Returns:
            pred (float): prediction of the given user/item pair.
        """
        if not self.awareness_constrain:
            x_known, y_known = False, False

            if x_id in self.x_list:
                x_known = True
            if y_id in self.y_list:
                y_known = True

            if not (x_known and y_known):
                # if self.uuCF:
                #     print(f"Can not predict rating of user {x_id} for item {y_id}.")
                # else:
                #     print(f"Can not predict rating of user {y_id} for item {x_id}.")
                return self.global_mean

        return _predict(x_id, y_id, self.x_rated[y_id], self.S, self.k, self.min_k)

    def __recommend(self, u):
        """Determine all items should be recommended for user u. (uuCF = 1)
        or all users who might have interest on item u (uuCF = 0)
        The decision is made based on all i such that: self.pred(u, i) > 0.
        Suppose we are considering items which have not been rated by u yet.
        NOT YET IMPLEMENTED...

        Args:
            u (int): user that we are recommending

        Returns:
            list: a list of movie that might suit user u
        """
        pass

    def rmse(self):
        """Calculate Root Mean Squared Error between the predictions and the ground truth.
        Print the RMSE.
        """
        mse = np.mean((self.predictions - self.ground_truth)**2)
        rmse_ = np.sqrt(mse)
        print(f"RMSE: {rmse_:.5f}")

    def mae(self):
        """Calculate Mean Absolute Error between the predictions and the ground truth.
        Print the MAE.
        """
        mae_ = np.mean(np.abs(self.predictions - self.ground_truth))
        print(f"MAE: {mae_:.5f}")
