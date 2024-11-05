import numpy as np
from matplotlib import pyplot as plt
from sklearn.svm import SVC
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import PCA

import duckdb

class SVMModel:
    def __init__(self, tfidf_pca_dataset_size: int=500, pca_max_n_components: int=100, min_dataset_size: int=25):
        self.tfidf_pca_dataset_size = tfidf_pca_dataset_size
        self.pca_max_n_components = pca_max_n_components
        self.min_dataset_size = min_dataset_size

        self.tfidf = None
        self.pca = None
        self.svm = None

    # ================================================
    # VISUALIZATION
    # ================================================
        
    def visualize_pca(self, X: np.ndarray, y: np.ndarray, input_is_embeddings: bool=True):
        if not (self.tfidf and self.pca):
            return False
        
        assert X.shape == (len(y), self.pca.n_components)
        X_pca = self.pca.transform(X) if not input_is_embeddings else X

        plt.figure(figsize=(10, 6))
        plt.scatter(X_pca[y == 0, 0], X_pca[y == 0, 1], label='Unliked', alpha=0.5)
        plt.scatter(X_pca[y == 1, 0], X_pca[y == 1, 1], label='Liked', alpha=0.5)
        plt.xlabel('First Principal Component')
        plt.ylabel('Second Principal Component')
        plt.title('PCA of Article Features')
        plt.legend()
        plt.savefig('pca_plot.png')
        plt.close()

    # ================================================
    # TRAINING & PREDICTION
    # ================================================

    def train_embeddings(self, dataset: list[str]):
        """
        Embedding = tfidf + pca
        Trains an embedding model on random subset of self.tfidf_pca_dataset_size articles
        (Valid datasets must have at least self.min_dataset_size articles)

        Sets and fits self.tfidf, self.pca, self.svm

        Args:
            dataset (list[str]): list of article descriptions

        Returns:
            bool: True if successful, False otherwise
        """
        if len(dataset) < self.min_dataset_size:
            return False
        if self.tfidf and self.pca: # don't retrain
            return True
        
        # extract features from article descriptions
        self.tfidf = TfidfVectorizer().fit(dataset)
        X = self.tfidf.transform(dataset)
        assert X.shape == (len(dataset), self.tfidf.get_feature_names_out().shape[0])

        # n_features is high; reduce dimensionality
        pca_n_components = min(X.shape[0]-1, X.shape[1]-1, self.pca_max_n_components)
        self.pca = PCA(n_components=pca_n_components).fit(X) # will give (n_samples, pca_n_components)

        return True
    
    def embed(self, dataset: list[str]):
        if not (self.tfidf and self.pca):
            return False

        return self.pca.transform(self.tfidf.transform(dataset))

    def train_svm(self, X: np.ndarray, y: np.ndarray, visualize: bool=False):
        """
        Trains an SVM on the given embeddings and labels
        Labels are 1 for liked, 0 for unliked

        Args:
            X (n_samples, pca_n_components): embeddings (tfidf + pca)
            y (n_samples,): labels (1 for liked, 0 for unliked)
            visualize (bool): whether to visualize the PCA (and dump plot to file)
        """
        if not (self.tfidf and self.pca):
            return False

        if visualize:
            self.visualize_pca(X, y, input_is_embeddings=True)

        self.svm = SVC(kernel='rbf', probability=True)
        self.svm.fit(X, y)

    def predict(self, X: np.ndarray):
        """
        Args:
            X (n_features): embeddings (tfidf + pca)

        Returns:
            array: predicted probabilities (n_samples,)
        """
        if not (self.svm):
            return False

        # class 1 is liked
        return self.svm.predict_proba(X)[:, 1].item()


# ================================================
#  UTILITIES
# ================================================

def gen_svm_data(conn: duckdb.DuckDBPyConnection):
    """
    Generates a dataset of articles for training the SVM
    (equal number of liked and unliked articles)

    Returns:
        tuple[np.ndarray, np.ndarray]: embeddings and labels
        (None, None) if there are no articles in the database
    """
    liked_articles = conn.sql('SELECT description, title, is_liked FROM articles WHERE is_liked = true').fetchall()

    if len(liked_articles) == 0:
        return None, None

    unliked_articles = conn.sql(f'SELECT description, title, is_liked FROM articles WHERE is_liked = false ORDER BY RANDOM() LIMIT {len(liked_articles)}').fetchall()
    X, y = zip(*[
        (article[0] + ' ' + article[1], article[2])
        for article in liked_articles + unliked_articles
        if article[0] and article[1]
    ])
    return X, np.array(y)

def gen_embeddings_data(conn: duckdb.DuckDBPyConnection):
    """
    Generates a dataset of articles for training the embeddings
    """
    return [
        article[0] + ' ' + article[1]
        for article in conn.sql('SELECT description, title FROM articles').fetchall()
        if article[0] and article[1]
    ]
