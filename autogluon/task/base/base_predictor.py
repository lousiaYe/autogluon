""" TODOs needed to get predictor object working for any task:

    - Base Task should implement @classmethod load(output_directory) method which restores a Predictor object from file (previously saved using Predictor.save(output_directory)). task.load(output_directory) can simply: return Predictor.load(output_directory)
    
    - Base Task.fit() needs to create Results object and assign it to predictor.results before returning predictor. The only thing task.fit should return is a single Predictor object.
    
    - Right before task.fit() returns predictor, it should call: predictor.save(outputdir) so that training progress is not accidentally lost.
    
    - task.fit() needs to have an output_directory argument where to store all outputs
    
    - Delete line "Results = collections.namedtuple('Results', 'model reward config time metadata')" from task.fit(), and store all info in self.results dict object defined below instead.
    
    - This code assumes trial_ids are sortable such that lower trial_id indicates trial was scheduled earlier than trial with higher trial_id
    
    - task object should have get_labels(Dataset) method
"""

import logging
from abc import ABC, abstractmethod
import pickle, json
from ...utils import plot_performance_vs_trials, plot_summary_of_models

logger = logging.getLogger(__name__)

__all__ = ['BasePredictor']

PREDICTOR_FILENAME = "predictor.pkl" # Filename in which predictor object is stored. Should be hardcoded so that user only needs to specify directory where to store all training-related output files.
RESULTS_FILENAME = "results.json" # Filename in which FitResults object is stored. Should be hardcoded so that user only needs to specify directory where to store all training-related output files.

class BasePredictor(ABC):
    """
    Base object returned by task.fit() for each task implemented in AutoGluon.

    Example user workflow for say image classification applications:
        # Training time:
        >>> from autogluon import image_classification as task
        >>> train_data = task.Dataset(traindata_filepath)
        >>> output_directory = '~/temp/' # any directory name specifying where to store all results
        >>> predictor = task.fit(train_data=train_data, output_directory=output_directory)
        >>> # To instead specify train/val split, do: predictor = task.fit(train_data=train_data, val_data=task.Dataset(valdata_filepath), output_directory=output_directory)
        >>> results = predictor.fit_summary() # will also print out summary and create plots
        # Inference time (may be a new Python session):
        >>> test_data = task.Dataset(testdata_filepath)
        >>> test_labels = task.get_labels(test_data)
        >>> predictor = None  # We delete predictor here just to demonstrate how to load previously-trained predictor from file
        >>> predictor = task.load(output_directory)
        >>> batch_predictions = predictor.predict(test_data)
        >>> performance = predictor.evaluate_predictions(y_true=test_labels, y_pred=batch_predictions)
        # or can instead just use equivalent shorthand: performance = predictor.evaluate(test_data)
        # Can also do inference on just a single test example: x_i = single datapoint, eg. x_i = test_data[i]
        >>> single_prediction = predictor.predict(x_i)
        >>> print((x_i, single_prediction))
    """
    def __init__(self, loss_func, eval_func, model=None, results=None, **kwargs):
        self.model = model # MXnet model or list of multiple models / ensemble. Each model should have its own loading/saving functionality.
        self.loss_func = loss_func # Loss function (or string name) minimized during training
        self.eval_func = eval_func # Evaluation function / metric applied on validation/test data to gauge predictive performance.
        # Note: we may save a lot of headache if higher values of this eval_func metric = better, consistently across all tasks.
        # self.results = self._createResults() # dict object to store all information during task.fit().
        self.results = results

    @abstractmethod
    def load(self, output_directory):
        """ Load Predictor object from given directory.
            Make sure to also load any models from files that exist in output_directory and set them = predictor.model.
        """
        filepath = output_directory + PREDICTOR_FILENAME
        results_file = output_directory + RESULTS_FILENAME
        predictor = pickle.load(open(filepath,"rb"))
        predictor.results = json.load(open(results_file,'r'))
        pass  # Need to load models and set them = predictor.model

    @abstractmethod
    def save(self, output_directory):
        """ Saves this object to file. Don't forget to save the models and the Results objects if they exist.
            Before returning a Predictor, task.fit() should call predictor.save()
        """
        filepath = output_directory + PREDICTOR_FILENAME
        self._save_model(output_directory)
        self._save_results(output_directory)
        self.model = None # Save model separately from Predictor object
        self.results = None # Save results separately from Predictor object
        pickle.dump(self, open(filepath,'wb'))
        logger.info("Predictor saved to file: " % filepath)

    def _save_results(self, output_directory):
        """ Internal helper function: Save results in human-readable file JSON format """
        results_file = output_directory + RESULTS_FILENAME
        json.dump(self.results, open(results_file, 'w'))

    @abstractmethod
    def _save_model(self, output_directory):
        """ Internal helper function: Save self.model object to file located in output_directory.
            For example, if self.model is MXNet model, can simply call self.model.save(output_directory+filename)
        """
        pass

    @abstractmethod
    def predict(self, X):
        """ This method should be able to produce predictions regardless if:
            X = single data example (e.g. single image, single document),
            X = batch of many examples, X = task.Dataset object
        """
        pass

    @abstractmethod
    def predict_proba(self, X):
        """ Produces predicted class probabilities if we are dealing with a classification task.
            In this case, predict() should just be a wrapper around this method to convert predicted probabilties to predicted class labels.
        """
        pass

    @abstractmethod
    def evaluate_predictions(self, y_true, y_pred):
        """ Evaluate the provided list of predictions against list of ground truth labels according to the task-specific evaluation metric (self.eval_func). """
        pass

    @abstractmethod
    def evaluate(self, dataset):
        """ Use self.model to produce predictions from the given Dataset object, and then compute task-specific evaluation metric (self.eval_func)
            comparing these predictions against ground truth labels stored in the Dataset object.
        """
        pass

    def fit_summary(self, output_directory, verbosity = 2):
        """
            Returns a summary of the fit process.
            Args:
                verbosity (int): how much output to print:
                <= 0 for no output printing, 1 for just high-level summary, 2 for summary and plot, >= 3 for all information contained in results object.
        """
        if verbosity > 0:
            summary = {}
            for k in self.results.keys():
                if k not in ['metadata', 'trial_info']:
                    summary[k] = self.results[k]
            logger.info("Summary of Fit Process:  ")
            logger.info(json.dumps(summary, indent=2))
            if len(self.results['metadata']) > 0:
                logger.info(json.dumps(self.results['metadata'], indent=2))

        if len(self.results['trial_info']) > 0 and  verbosity > 1:
            ordered_trials = sorted(self.results['trial_info'].keys())
            if verbosity > 2:
                for trial_id in ordered_trials:
                    logger.info("Information about each trial:  ")
                    logger.info("Trial ID: %s" % trial_id)
                    logger.info(json.dumps(self.results['trial_info'][trial_id], indent=2))

            # Create plot summaries:
            plot_summary_of_models(self.results, output_directory)
            plot_performance_vs_trials(self.results, output_directory)
        return self.results
    
    def _createResults(self):
        """ Internal helper function: Dict object to store all relevant information produced during task.fit(). 
            Empty for now, but should be updated during task.fit().
            All tasks should adhere to this same template for consistency.
        """
        results = {}
        results['time'] = None # run-time of task.fit()
        results['num_trials_completed'] = None # number of trials completed during task.fit() 
        results['best_hyperparameters'] = None # hyperparameter values corresponding to the chosen model in self.model
        results['validation_perf'] = None # validation performance achieved by the chosen model (what is currently called 'reward')
        results['training_loss'] = None # training loss value achieved by the chosen model (on the training data)
        results['search_space'] = None # hyperparameter search space considered in task.fit()
        results['search_strategy'] = None # HPO algorithm used (ie. Hyperband, random, BayesOpt). If the HPO algorithm used kwargs, then this should be tuple (HPO_algorithm_string, HPO_kwargs)
        
        results['metadata'] = {} # dict containing other optional metadata with keys. For example:
        # latency = inference-time of self.model (time for feedforward pass)
        # memory = amount of memory required by self.model
        
        results['trial_info'] = {} # dict with keys = trial_IDs, values = dict of information about each individual trial (length = results['num_trials_completed'])
        """ Example of what one element of this dict must look like: 
        
        results['trial_info'][trial_id] =  {
            'config' : hyperparameter configuration tried in this trial
            'validation_perf' : validation performance achieved by the model from this trial
            'training_loss' : training loss value achieved by the model from this trial (on the training data)
            'metadata' : dict of various optional metadata with keys such as: latency, memory, time, early_stopped, etc.
        }
        
        """
        return results