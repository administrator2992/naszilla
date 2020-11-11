import numpy as np
import pickle
import sys
import os

# todo check if it works to import these within each data class
from nasbench import api
from nas_201_api import NASBench201API as API
sys.path.append('../nasbench301')
#import nasbench301 as nb

from nas_bench_101.cell_101 import Cell101
from nas_bench_201.cell_201 import Cell201
#from nas_bench_301.cell_301 import Cell301

class Nasbench:

    def get_cell(self, arch=None):
        return None

    def query_arch(self, 
                   arch=None, 
                   train=True, 
                   predictor_encoding=None, 
                   cutoff=0,
                   random_encoding='adj',
                   deterministic=True,
                   noise_factor=1,
                   epochs=0,
                   random_hash=False,
                   max_edges=None,
                   max_nodes=None):

        arch_dict = {}
        arch_dict['epochs'] = epochs

        if arch is None:

            arch = self.get_cell().random_cell(self.nasbench,
                                               random_encoding=random_encoding, 
                                               max_edges=max_edges, 
                                               max_nodes=max_nodes,
                                               cutoff=cutoff,
                                               index_hash=self.index_hash)
        arch_dict['spec'] = arch

        if predictor_encoding:
            arch_dict['encoding'] = self.get_cell(arch).encode(predictor_encoding=predictor_encoding,
                                                                 nasbench=self.nasbench,
                                                                 deterministic=deterministic,
                                                                 cutoff=cutoff)

        if train:
            arch_dict['val_loss'] = self.get_cell(arch).get_val_loss(self.nasbench, 
                                                                       deterministic=deterministic,
                                                                       dataset=self.dataset,
                                                                       noise_factor=noise_factor)
            arch_dict['test_loss'] = self.get_cell(arch).get_test_loss(self.nasbench,
                                                                         dataset=self.dataset,
                                                                         noise_factor=noise_factor)
            arch_dict['num_params'] = self.get_cell(arch).get_num_params(self.nasbench)
            arch_dict['val_per_param'] = (arch_dict['val_loss'] - 4.8) * (arch_dict['num_params'] ** 0.5) / 100

            if self.get_type() == 'nasbench_101':
                arch_dict['dist_to_min'] = arch_dict['val_loss'] - 4.94457682
            elif self.get_type() == 'nasbench_301':
                arch_dict['dist_to_min'] = arch_dict['val_loss'] - 4
            elif self.dataset == 'cifar10':
                arch_dict['dist_to_min'] = arch_dict['val_loss'] - 8.3933
            elif self.dataset == 'cifar100':
                arch_dict['dist_to_min'] = arch_dict['val_loss'] - 26.5067
            elif self.dataset in ['ImageNet16-120', 'imagenet']:
                arch_dict['dist_to_min'] = arch_dict['val_loss'] - 53.2333
            else:
                print('invalid search space / dataset in data.py')
                sys.exit()

        return arch_dict

    def mutate_arch(self, 
                    arch, 
                    mutation_rate=1.0, 
                    mutate_encoding='adj',
                    cutoff=0):

        return self.get_cell(arch).mutate(self.nasbench,
                                            mutation_rate=mutation_rate,
                                            mutate_encoding=mutate_encoding,
                                            index_hash=self.index_hash,
                                            cutoff=cutoff)

    def generate_random_dataset(self,
                                num=10, 
                                train=True,
                                predictor_encoding=None, 
                                random_encoding='adj',
                                deterministic_loss=True,
                                noise_factor=1,
                                patience_factor=5,
                                allow_isomorphisms=False,
                                cutoff=0,
                                max_edges=None,
                                max_nodes=None):
        """
        create a dataset of randomly sampled architectues
        test for isomorphisms using a hash map of path indices
        use patience_factor to avoid infinite loops
        """
        data = []
        dic = {}
        tries_left = num * patience_factor
        while len(data) < num:
            tries_left -= 1
            if tries_left <= 0:
                break

            arch_dict = self.query_arch(train=train,
                                        predictor_encoding=predictor_encoding,
                                        random_encoding=random_encoding,
                                        deterministic=deterministic_loss,
                                        noise_factor=noise_factor,
                                        cutoff=cutoff,
                                        max_edges=max_edges,
                                        max_nodes=max_nodes)

            h = self.get_hash(arch_dict['spec'])

            if allow_isomorphisms or h not in dic:
                dic[h] = 1
                data.append(arch_dict)
        return data


    def get_candidates(self, 
                       data, 
                       num=100,
                       acq_opt_type='mutation',
                       predictor_encoding=None,
                       mutate_encoding='adj',
                       loss='val_loss',
                       allow_isomorphisms=False, 
                       patience_factor=5, 
                       deterministic_loss=True,
                       noise_factor=1,
                       num_arches_to_mutate=1,
                       max_mutation_rate=1,
                       train=False,
                       cutoff=0):
        """
        Creates a set of candidate architectures with mutated and/or random architectures
        """

        candidates = []
        # set up hash map
        dic = {}
        for d in data:
            arch = d['spec']
            h = self.get_hash(arch)
            dic[h] = 1

        if acq_opt_type in ['mutation', 'mutation_random']:
            # mutate architectures with the lowest loss
            best_arches = [arch['spec'] for arch in sorted(data, key=lambda i:i[loss])[:num_arches_to_mutate * patience_factor]]

            # stop when candidates is size num
            # use patience_factor instead of a while loop to avoid long or infinite runtime

            for arch in best_arches:
                if len(candidates) >= num:
                    break
                for i in range(int(num / num_arches_to_mutate / max_mutation_rate)):
                    for rate in range(1, max_mutation_rate + 1):
                        mutated = self.mutate_arch(arch, 
                                                   mutation_rate=rate, 
                                                   mutate_encoding=mutate_encoding)
                        arch_dict = self.query_arch(mutated, 
                                                    train=train,
                                                    predictor_encoding=predictor_encoding,
                                                    deterministic=deterministic_loss,
                                                    noise_factor=noise_factor,
                                                    cutoff=cutoff)
                        h = self.get_hash(mutated)

                        if allow_isomorphisms or h not in dic:
                            dic[h] = 1    
                            candidates.append(arch_dict)

        if acq_opt_type in ['random', 'mutation_random']:
            # add randomly sampled architectures to the set of candidates
            for _ in range(num * patience_factor):
                if len(candidates) >= 2 * num:
                    break

                arch_dict = self.query_arch(train=train, 
                                            noise_factor=noise_factor,
                                            predictor_encoding=predictor_encoding,
                                            cutoff=cutoff)
                h = self.get_hash(arch_dict['spec'])

                if allow_isomorphisms or h not in dic:
                    dic[h] = 1
                    candidates.append(arch_dict)

        return candidates

    def remove_duplicates(self, candidates, data):
        # input: two sets of architectues: candidates and data
        # output: candidates with arches from data removed

        dic = {}
        for d in data:
            dic[self.get_hash(d['spec'])] = 1
        unduplicated = []
        for candidate in candidates:
            if self.get_hash(candidate['spec']) not in dic:
                dic[self.get_hash(candidate['spec'])] = 1
                unduplicated.append(candidate)
        return unduplicated

    def train_test_split(self, data, train_size, 
                                     shuffle=True, 
                                     rm_duplicates=True):
        if shuffle:
            np.random.shuffle(data)
        traindata = data[:train_size]
        testdata = data[train_size:]

        if rm_duplicates:
            self.remove_duplicates(testdata, traindata)
        return traindata, testdata


    def encode_data(self, dicts):
        # input: list of arch dictionary objects
        # output: xtrain (in binary path encoding), ytrain (val loss)

        data = []
        for dic in dicts:
            arch = dic['spec']
            encoding = Arch(arch).encode_paths()
            data.append((arch, encoding, dic['val_loss_avg'], None))
        return data

    def get_arch_list(self,
                      aux_file_path,
                      distance=None,
                      iteridx=0,
                      num_top_arches=5,
                      max_edits=20,
                      num_repeats=5,
                      random_encoding='adj',
                      verbose=0):
        # Method used for gp_bayesopt

        # load the list of architectures chosen by bayesopt so far
        base_arch_list = pickle.load(open(aux_file_path, 'rb'))
        top_arches = [archtuple[0] for archtuple in base_arch_list[:num_top_arches]]
        if verbose:
            top_5_loss = [archtuple[1][0] for archtuple in base_arch_list[:min(5, len(base_arch_list))]]
            print('top 5 val losses {}'.format(top_5_loss))

        # perturb the best k architectures    
        dic = {}
        for archtuple in base_arch_list:
            path_indices = self.get_cell(archtuple[0]).get_path_indices()
            dic[path_indices] = 1

        new_arch_list = []
        for arch in top_arches:
            for edits in range(1, max_edits):
                for _ in range(num_repeats):
                    #perturbation = Cell(**arch).perturb(self.nasbench, edits)
                    perturbation = self.get_cell(arch).mutate(self.nasbench, edits)
                    path_indices = self.get_cell(perturbation).get_path_indices()
                    if path_indices not in dic:
                        dic[path_indices] = 1
                        new_arch_list.append(perturbation)

        # make sure new_arch_list is not empty
        while len(new_arch_list) == 0:
            for _ in range(100):
                arch = self.get_cell().random_cell(self.nasbench, random_encoding=random_encoding)
                path_indices = self.get_cell(arch).get_path_indices()
                if path_indices not in dic:
                    dic[path_indices] = 1
                    new_arch_list.append(arch)

        return new_arch_list

    # Method used for gp_bayesopt for nasbench
    @classmethod
    def generate_distance_matrix(cls, arches_1, arches_2, distance):
        matrix = np.zeros([len(arches_1), len(arches_2)])
        for i, arch_1 in enumerate(arches_1):
            for j, arch_2 in enumerate(arches_2):
                matrix[i][j] = self.get_cell(arch_1).distance(self.get_cell(arch_2), dist_type=distance)
        return matrix


class Nasbench101(Nasbench):

    def __init__(self,
               data_folder='~/nas_benchmark_datasets/',
               index_hash_folder='./',
               mf=False):
        self.mf = mf
        self.dataset = 'cifar10'

        """
        For NAS encodings experiments, some of the path-based encodings currently require a
        hash map from path indices to cell architectuers. We have created a pickle file which
        contains the hash map, located at 
        https://drive.google.com/file/d/1yMRFxT6u3ZyfiWUPhtQ_B9FbuGN3X-Nf/view?usp=sharing
        """
        self.index_hash = None
        index_hash_path = os.path.expanduser(index_hash_folder + 'index_hash.pkl')
        if os.path.isfile(index_hash_path):
            self.index_hash = pickle.load(open(index_hash_path, 'rb'))

        if not self.mf:
            self.nasbench = api.NASBench(os.path.expanduser(data_folder + 'nasbench_only108.tfrecord'))
        else:
            self.nasbench = api.NASBench(os.path.expanduser(data_folder + 'nasbench_full.tfrecord'))

    def get_cell(self, arch=None):
        if not arch:
            return Cell101
        else:
            return Cell101(**arch)

    def get_type(self):
        return 'nasbench_101'

    def convert_to_cells(self,
                         arches,
                         predictor_encoding='path',
                         cutoff=0,
                         train=True):
        cells = []
        for arch in arches:
            spec = Cell.convert_to_cell(arch)
            cell = self.query_arch(spec,
                                   predictor_encoding=predictor_encoding,
                                   cutoff=cutoff,
                                   train=train)
            cells.append(cell)
        return cells

    def get_nbhd(self, arch, mutate_encoding='adj'):
        return Cell101(**arch).get_neighborhood(self.nasbench, 
                                                mutate_encoding=mutate_encoding,
                                                index_hash=self.index_hash)

    def get_hash(self, arch):
        # return a unique hash of the architecture+fidelity
        return Cell101(**arch).get_path_indices()
        

class Nasbench201(Nasbench):

    def __init__(self,
                 dataset='cifar10',
                 data_folder='~/nas_benchmark_datasets/',
                 version='1_0'):
        self.search_space = 'nasbench_201'
        self.dataset = dataset
        self.index_hash = None

        if version == '1_0':
            self.nasbench = API(os.path.expanduser(nas_benchmarks_folder + 'NAS-Bench-201-v1_0-e61699.pth'))
        elif version == '1_1':
            self.nasbench = API(os.path.expanduser(nas_benchmarks_folder + 'NAS-Bench-201-v1_1-096897.pth'))

    def get_type(self):
        return 'nasbench_201'

    def get_cell(self, arch=None):
        if not arch:
            return Cell201
        else:
            return Cell201(**arch)

    def get_nbhd(self, arch, mutate_encoding='adj'):
        return Cell201(**arch).get_neighborhood(self.nasbench, 
                                                mutate_encoding=mutate_encoding)

    def get_hash(self, arch):
        # return a unique hash of the architecture+fidelity
        return Cell201(**arch).get_string()

class Nasbench301(Nasbench):

    def __init__(self):
        self.dataset = 'cifar10'
        self.search_space = 'nasbench_301'
        ensemble_dir_performance = os.path.expanduser('~/nasbench301/nasbench301_models_v0.9/xgb_v0.9')
        performance_model = nb.load_ensemble(ensemble_dir_performance)
        ensemble_dir_runtime = os.path.expanduser('~/nasbench301/nasbench301_models_v0.9/lgb_runtime_v0.9')
        runtime_model = nb.load_ensemble(ensemble_dir_runtime)
        self.nasbench = [performance_model, runtime_model] 
        self.index_hash = None

    def get_type(self):
        return 'nasbench_301'

    def get_cell(self, arch=None):
        if not arch:
            return Cell301
        else:
            return Cell301(**arch)

    def get_nbhd(self, arch, mutate_encoding='adj'):
        return Cell301(**arch).get_neighborhood(self.nasbench, 
                                                mutate_encoding=mutate_encoding)

    def get_hash(self, arch):
        # return a unique hash of the architecture+fidelity
        return Cell301(**arch).serialize()
