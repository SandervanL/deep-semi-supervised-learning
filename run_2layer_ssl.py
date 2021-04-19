import sys
import learn_yz_x_ss

print('Usage: python [this_script.py] [n_labels] [seed] [n_hidden]')
n_labels = int(sys.argv[1])
print('n_labels:', n_labels)
seed = int(sys.argv[2])
print('seed:', seed)
n_hidden = int(sys.argv[3])

if n_labels not in (100, 600, 1000, 3000):
    print(
        'WARNING: for MNIST, n_labels should be in (100,600,1000,3000), otherwise the number of datapoints might not be a multiple of the number of minibatches.')
learn_yz_x_ss.main(3000, n_labels, dataset='mnist_2layer', n_z=50, n_hidden=(n_hidden,), seed=seed, alpha=0.1, n_minibatches=100, comment='')
