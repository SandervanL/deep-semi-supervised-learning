import inspect

import numpy as np
import theano
import theano.tensor as T

import anglepy as ap
import anglepy.ndict as ndict
from anglepy.misc import lazytheanofunc


# import theano.sandbox.cuda.rng_curand as rng_curand

def shared32(x, name=None, borrow=False):
    return theano.shared(np.asarray(x, dtype='float32'), name=name, borrow=borrow)


'''
Fully connected deep variational auto-encoder (VAE_Z_X)
'''


class GPUVAE_Z_X(ap.GPUVAEModel):

    def __init__(self, get_optimizer, n_x, n_hidden_q, n_z, n_hidden_p, nonlinear_q='tanh', nonlinear_p='tanh',
                 type_px='bernoulli', type_qz='gaussianmarg', type_pz='gaussianmarg', prior_sd=1, init_sd=1e-2,
                 var_smoothing=0, n_mixture=50):
        self.constr = (__name__, inspect.stack()[0][3], locals())
        self.n_x = n_x
        self.n_hidden_q = n_hidden_q
        self.n_z = n_z
        self.n_hidden_p = n_hidden_p
        self.dropout = False
        self.nonlinear_q = nonlinear_q
        self.nonlinear_p = nonlinear_p
        self.type_px = type_px
        self.type_qz = type_qz
        self.type_pz = type_pz
        self.prior_sd = prior_sd
        self.var_smoothing = var_smoothing
        self.n_mixture = n_mixture

        # Init weights
        v, w = self.init_w(1e-2)
        for i in v:
            v[i] = shared32(v[i])
        for i in w:
            w[i] = shared32(w[i])
        self.v = v
        self.w = w

        super(GPUVAE_Z_X, self).__init__(get_optimizer)

    def factors(self, x, z, A):

        v = self.v
        w = self.w

        '''
        z is unused
        x['x'] is the data
        
        The names of dict z[...] may be confusing here: the latent variable z is not included in the dict z[...],
        but implicitely computed from epsilon and parameters in w.

        z is computed with g(.) from eps and variational parameters
        let logpx be the generative model density: log p(x|z) where z=g(.)
        let logpz be the prior of Z plus the entropy of q(z|x): logp(z) + H_q(z|x)
        So the lower bound L(x) = logpx + logpz
        
        let logpv and logpw be the (prior) density of the parameters
        '''

        # Compute q(z|x)
        hidden_q = [x['x']]

        def f_softplus(x):
            return T.log(T.exp(x) + 1)  # - np.log(2)

        def f_rectlin(x):
            return x * (x > 0)

        def f_rectlin2(x):
            return x * (x > 0) + 0.01 * x

        nonlinear = {'tanh': T.tanh, 'sigmoid': T.nnet.sigmoid, 'softplus': f_softplus, 'rectlin': f_rectlin,
                     'rectlin2': f_rectlin2}
        nonlinear_q = nonlinear[self.nonlinear_q]
        nonlinear_p = nonlinear[self.nonlinear_p]

        # rng = rng_curand.CURAND_RandomStreams(0)
        import theano.tensor.shared_randomstreams
        rng = theano.tensor.shared_randomstreams.RandomStreams(0)

        # TOTAL HACK
        # hidden_q.append(nonlinear_q(T.dot(v['scale0'], A) * T.dot(w['out_w'].T, hidden_q[-1]) + T.dot(v['b0'], A)))
        # hidden_q.append(nonlinear_q(T.dot(v['scale1'], A) * T.dot(w['w1'].T, hidden_q[-1]) + T.dot(v['b1'], A)))
        for i in range(len(self.n_hidden_q)):
            hidden_q.append(nonlinear_q(T.dot(v['w' + str(i)], hidden_q[-1]) + T.dot(v['b' + str(i)], A)))
            if self.dropout:
                hidden_q[-1] *= 2. * (rng.uniform(size=hidden_q[-1].shape, dtype='float32') > .5)

        q_mean = T.dot(v['mean_w'], hidden_q[-1]) + T.dot(v['mean_b'], A)
        if self.type_qz == 'gaussian' or self.type_qz == 'gaussianmarg':
            q_logvar = T.dot(v['logvar_w'], hidden_q[-1]) + T.dot(v['logvar_b'], A)
        else:
            raise Exception()

        # function for distribution q(z|x)
        theanofunc = lazytheanofunc('warn', mode='FAST_RUN')
        self.dist_qz['z'] = theanofunc([x['x']] + [A], [q_mean, q_logvar])

        # Compute virtual sample
        eps = rng.normal(size=q_mean.shape, dtype='float32')
        _z = q_mean + T.exp(0.5 * q_logvar) * eps

        # Compute log p(x|z)
        hidden_p = [_z]
        for i in range(len(self.n_hidden_p)):
            hidden_p.append(nonlinear_p(T.dot(w['w' + str(i)], hidden_p[-1]) + T.dot(w['b' + str(i)], A)))
            if self.dropout:
                hidden_p[-1] *= 2. * (rng.uniform(size=hidden_p[-1].shape, dtype='float32') > .5)

        if self.type_px == 'bernoulli':
            p = T.nnet.sigmoid(T.dot(w['out_w'], hidden_p[-1]) + T.dot(w['out_b'], A))
            _logpx = - T.nnet.binary_crossentropy(p, x['x'])
            self.dist_px['x'] = theanofunc([_z] + [A], p)
        elif self.type_px == 'gaussian':
            x_mean = T.dot(w['out_w'], hidden_p[-1]) + T.dot(w['out_b'], A)
            x_logvar = T.dot(w['out_logvar_w'], hidden_p[-1]) + T.dot(w['out_logvar_b'], A)
            _logpx = ap.logpdfs.normal2(x['x'], x_mean, x_logvar)
            self.dist_px['x'] = theanofunc([_z] + [A], [x_mean, x_logvar])
        elif self.type_px == 'bounded01':
            x_mean = T.nnet.sigmoid(T.dot(w['out_w'], hidden_p[-1]) + T.dot(w['out_b'], A))
            x_logvar = T.dot(w['out_logvar_b'], A)
            _logpx = ap.logpdfs.normal2(x['x'], x_mean, x_logvar)
            # Make it a mixture between uniform and Gaussian
            w_unif = T.nnet.sigmoid(T.dot(w['out_unif'], A))
            _logpx = T.log(w_unif + (1 - w_unif) * T.exp(_logpx))
            self.dist_px['x'] = theanofunc([_z] + [A], [x_mean, x_logvar])
        else:
            raise Exception("")

        # Note: logpx is a row vector (one element per sample)
        logpx = T.dot(shared32(np.ones((1, self.n_x))), _logpx)  # logpx = log p(x|z,w)

        # log p(z) (prior of z)
        if self.type_pz == 'gaussianmarg':
            logpz = -0.5 * (np.log(2 * np.pi) + (q_mean ** 2 + T.exp(q_logvar))).sum(axis=0, keepdims=True)
        elif self.type_pz == 'gaussian':
            logpz = ap.logpdfs.standard_normal(_z).sum(axis=0, keepdims=True)
        elif self.type_pz == 'mog':
            pz = 0
            for i in range(self.n_mixture):
                pz += T.exp(
                    ap.logpdfs.normal2(_z, T.dot(w['mog_mean' + str(i)], A), T.dot(w['mog_logvar' + str(i)], A)))
            logpz = T.log(pz).sum(axis=0, keepdims=True) - self.n_z * np.log(float(self.n_mixture))
        elif self.type_pz == 'laplace':
            logpz = ap.logpdfs.standard_laplace(_z).sum(axis=0, keepdims=True)
        elif self.type_pz == 'studentt':
            logpz = ap.logpdfs.studentt(_z, T.dot(T.exp(w['logv']), A)).sum(axis=0, keepdims=True)
        else:
            raise Exception("Unknown type_pz")

        # loq q(z|x) (entropy of z)
        if self.type_qz == 'gaussianmarg':
            logqz = - 0.5 * (np.log(2 * np.pi) + 1 + q_logvar).sum(axis=0, keepdims=True)
        elif self.type_qz == 'gaussian':
            logqz = ap.logpdfs.normal2(_z, q_mean, q_logvar).sum(axis=0, keepdims=True)
        else:
            raise Exception()

        # [new part] Fisher divergence of latent variables
        if self.var_smoothing > 0:
            dlogq_dz = T.grad(logqz.sum(), _z)  # gives error when using gaussianmarg instead of gaussian
            dlogp_dz = T.grad((logpx + logpz).sum(), _z)
            FD = 0.5 * ((dlogq_dz - dlogp_dz) ** 2).sum(axis=0, keepdims=True)
            # [end new part]
            logqz -= self.var_smoothing * FD

        # Note: logpv and logpw are a scalars
        if True:
            def f_prior(_w, prior_sd=self.prior_sd):
                return ap.logpdfs.normal(_w, 0, prior_sd).sum()
        else:
            def f_prior(_w, prior_sd=self.prior_sd):
                return ap.logpdfs.standard_laplace(_w / prior_sd).sum()

        return logpx, logpz, logqz

    # Generate epsilon from prior
    def gen_eps(self, n_batch):
        z = {'eps': np.random.standard_normal(size=(self.n_z, n_batch)).astype('float32')}
        return z

    # Generate variables
    def gen_xz(self, x, z, n_batch):

        x, z = ndict.ordereddicts((x, z))

        A = np.ones((1, n_batch)).astype(np.float32)
        for i in z:
            z[i] = z[i].astype(np.float32)
        for i in x:
            x[i] = x[i].astype(np.float32)

        _z = {}

        # If x['x'] was given but not z['z']: generate z ~ q(z|x)
        if 'x' in x and 'z' not in z:

            q_mean, q_logvar = self.dist_qz['z'](*([x['x']] + [A]))
            _z['mean'] = q_mean
            _z['logvar'] = q_logvar

            # Require epsilon
            if 'eps' not in z:
                eps = self.gen_eps(n_batch)['eps']

            z['z'] = q_mean + np.exp(0.5 * q_logvar) * eps

        elif 'z' not in z:
            if self.type_pz in ['gaussian', 'gaussianmarg']:
                z['z'] = np.random.standard_normal(size=(self.n_z, n_batch)).astype(np.float32)
            elif self.type_pz == 'laplace':
                z['z'] = np.random.laplace(size=(self.n_z, n_batch)).astype(np.float32)
            elif self.type_pz == 'studentt':
                z['z'] = np.random.standard_t(np.dot(np.exp(self.w['logv'].get_value()), A)).astype(np.float32)
            elif self.type_pz == 'mog':
                i = np.random.randint(self.n_mixture)
                loc = np.dot(self.w['mog_mean' + str(i)].get_value(), A)
                scale = np.dot(np.exp(.5 * self.w['mog_logvar' + str(i)].get_value()), A)
                z['z'] = np.random.normal(loc=loc, scale=scale).astype(np.float32)
            else:
                raise Exception('Unknown type_pz')
        # Generate from p(x|z)

        if self.type_px == 'bernoulli':
            p = self.dist_px['x'](*([z['z']] + [A]))
            _z['x'] = p
            if 'x' not in x:
                x['x'] = np.random.binomial(n=1, p=p)
        elif self.type_px == 'bounded01' or self.type_px == 'gaussian':
            x_mean, x_logvar = self.dist_px['x'](*([z['z']] + [A]))
            _z['x'] = x_mean
            if 'x' not in x:
                x['x'] = np.random.normal(x_mean, np.exp(x_logvar / 2))
                if self.type_px == 'bounded01':
                    x['x'] = np.maximum(np.zeros(x['x'].shape), x['x'])
                    x['x'] = np.minimum(np.ones(x['x'].shape), x['x'])

        else:
            raise Exception("")

        return x, z, _z

    def variables(self):

        z = {}

        # Define observed variables 'x'
        x = {'x': T.fmatrix('x')}

        return x, z

    def init_w(self, std=1e-2):

        def rand(size):
            if len(size) == 2 and size[1] > 1:
                return np.random.normal(0, 1, size=size) / np.sqrt(size[1])
            return np.random.normal(0, std, size=size)

        v = {}
        # v['scale0'] = np.ones((self.n_hidden_q[0], 1))
        # v['scale1'] = np.ones((self.n_hidden_q[0], 1))

        v['w0'] = rand((self.n_hidden_q[0], self.n_x))
        v['b0'] = rand((self.n_hidden_q[0], 1))
        for i in range(1, len(self.n_hidden_q)):
            v['w' + str(i)] = rand((self.n_hidden_q[i], self.n_hidden_q[i - 1]))
            v['b' + str(i)] = rand((self.n_hidden_q[i], 1))

        v['mean_w'] = rand((self.n_z, self.n_hidden_q[-1]))
        v['mean_b'] = rand((self.n_z, 1))
        if self.type_qz in ['gaussian', 'gaussianmarg']:
            v['logvar_w'] = np.zeros((self.n_z, self.n_hidden_q[-1]))
        v['logvar_b'] = np.zeros((self.n_z, 1))

        w = {}

        if self.type_pz == 'mog':
            for i in range(self.n_mixture):
                w['mog_mean' + str(i)] = rand((self.n_z, 1))
                w['mog_logvar' + str(i)] = rand((self.n_z, 1))
        if self.type_pz == 'studentt':
            w['logv'] = np.zeros((self.n_z, 1))

        if len(self.n_hidden_p) > 0:
            w['w0'] = rand((self.n_hidden_p[0], self.n_z))
            w['b0'] = rand((self.n_hidden_p[0], 1))
            for i in range(1, len(self.n_hidden_p)):
                w['w' + str(i)] = rand((self.n_hidden_p[i], self.n_hidden_p[i - 1]))
                w['b' + str(i)] = rand((self.n_hidden_p[i], 1))
            w['out_w'] = rand((self.n_x, self.n_hidden_p[-1]))
            w['out_b'] = np.zeros((self.n_x, 1))
            if self.type_px == 'gaussian':
                w['out_logvar_w'] = rand((self.n_x, self.n_hidden_p[-1]))
                w['out_logvar_b'] = np.zeros((self.n_x, 1))
            if self.type_px == 'bounded01':
                w['out_logvar_b'] = np.zeros((self.n_x, 1))
                w['out_unif'] = np.zeros((self.n_x, 1))

        else:
            w['out_w'] = rand((self.n_x, self.n_z))
            w['out_b'] = np.zeros((self.n_x, 1))
            if self.type_px == 'gaussian':
                w['out_logvar_w'] = rand((self.n_x, self.n_z))
                w['out_logvar_b'] = np.zeros((self.n_x, 1))
            if self.type_px == 'bounded01':
                w['out_logvar_b'] = np.zeros((self.n_x, 1))
                w['out_unif'] = np.zeros((self.n_x, 1))

        return v, w
