#!/usr/bin/env python
"""Test dmd module"""
from __future__ import division
from future.builtins import range
import copy
import unittest
import os
from os.path import join
from shutil import rmtree

import numpy as np

import modred.parallel as parallel
from modred.dmd import *
from modred.vectorspace import *
import modred.vectors as V
from modred import util


#@unittest.skip('Testing something else.')
@unittest.skipIf(parallel.is_distributed(), 'Serial only.')
class TestDMDArraysFunctions(unittest.TestCase):
    def setUp(self):
        # Generate vecs if we are on the first processor
        # A random matrix of data (#cols = #vecs)
        self.num_vecs = 10
        self.num_states = 20


    def _helper_compute_DMD_from_data(
        self, vecs, inner_product, adv_vecs=None, max_num_eigvals=None):
        if adv_vecs is None:
            adv_vecs = vecs[:, 1:]
            vecs = vecs[:, :-1]
        correlation_mat = inner_product(vecs, vecs)
        cross_correlation_mat = inner_product(vecs, adv_vecs)
        V, Sigma, dummy = util.svd(correlation_mat)     # dummy = V.T
        U = vecs.dot(V).dot(np.diag(Sigma ** -0.5))

        # Truncate if necessary
        if max_num_eigvals is not None and (
            max_num_eigvals < Sigma.size):
            V = V[:, :max_num_eigvals]
            Sigma = Sigma[:max_num_eigvals]
            U = U[:, :max_num_eigvals]

        A_tilde = inner_product(
            U, adv_vecs).dot(V).dot(np.diag(Sigma ** -0.5))
        eigvals, W, Z = util.eig_biorthog(
            A_tilde, scale_choice='left')
        build_coeffs_proj = V.dot(np.diag(Sigma ** -0.5)).dot(W)
        build_coeffs_exact = (
            V.dot(np.diag(Sigma ** -0.5)).dot(W).dot(np.diag(eigvals ** -1.)))
        modes_proj = vecs.dot(build_coeffs_proj)
        modes_exact = adv_vecs.dot(build_coeffs_exact)
        adj_modes = U.dot(Z)
        spectral_coeffs = np.abs(np.array(
            inner_product(adj_modes, np.mat(vecs[:, 0]).T)).squeeze())
        return (
            modes_exact, modes_proj, spectral_coeffs, eigvals,
            W, Z, Sigma, V, correlation_mat, cross_correlation_mat)


    def _helper_test_mat_to_sign(
        self, true_vals, test_vals, rtol=1e-12, atol=1e-16):
        # Check that shapes are the same
        self.assertEqual(len(true_vals.shape), len(test_vals.shape))
        for shape_idx in range(len(true_vals.shape)):
            self.assertEqual(
                true_vals.shape[shape_idx], test_vals.shape[shape_idx])

        # Check values column by columns.  To allow for matrices or arrays,
        # turn columns into arrays and squeeze them (forcing 1D arrays).  This
        # avoids failures due to trivial shape mismatches.
        for col_idx in range(true_vals.shape[1]):
            true_col = np.array(true_vals[:, col_idx]).squeeze()
            test_col = np.array(test_vals[:, col_idx]).squeeze()
            self.assertTrue(
                np.allclose(true_col, test_col, rtol=rtol, atol=atol)
                or
                np.allclose(-true_col, test_col, rtol=rtol, atol=atol))


    def _helper_check_decomp(
        self, method_type, vecs, mode_indices, inner_product,
        inner_product_weights, rtol, atol, adv_vecs=None,
        max_num_eigvals=None):

        # Compute reference values for testing DMD computation
        (modes_exact_true, modes_proj_true, spectral_coeffs_true,
            eigvals_true, R_low_order_eigvecs_true, L_low_order_eigvecs_true,
            correlation_mat_eigvals_true, correlation_mat_eigvecs_true,
            correlation_mat_true, cross_correlation_mat_true) = (
            self._helper_compute_DMD_from_data(
            vecs, inner_product, adv_vecs=adv_vecs,
            max_num_eigvals=max_num_eigvals))

        # Compute DMD using modred method of choice
        if method_type == 'snaps':
            (modes_exact, modes_proj, spectral_coeffs, eigvals,
                R_low_order_eigvecs, L_low_order_eigvecs,
                correlation_mat_eigvals, correlation_mat_eigvecs,
                correlation_mat, cross_correlation_mat) = (
                compute_DMD_matrices_snaps_method(
                vecs, mode_indices, adv_vecs=adv_vecs,
                inner_product_weights=inner_product_weights,
                max_num_eigvals=max_num_eigvals, return_all=True))
        elif method_type == 'direct':
            (modes_exact, modes_proj, spectral_coeffs, eigvals,
                R_low_order_eigvecs, L_low_order_eigvecs,
                correlation_mat_eigvals, correlation_mat_eigvecs) = (
                compute_DMD_matrices_direct_method(
                vecs, mode_indices, adv_vecs=adv_vecs,
                inner_product_weights=inner_product_weights,
                max_num_eigvals=max_num_eigvals, return_all=True))
        else:
            raise ValueError('Invalid DMD matrix method.')

        # Compare values to reference values, allowing for sign differences in
        # some cases.  For the low-order eigenvectors, check that the elements
        # differ at most by a sign, as the eigenvectors may vary by sign even
        # element-wise.  This is due to the fact that the low-order linear maps
        # may have sign differences, as they depend on the correlation matrix
        # eigenvectors, which themselves may have column-wise sign differences.
        self._helper_test_mat_to_sign(
            modes_exact, modes_exact_true[:, mode_indices], rtol=rtol,
            atol=atol)
        self._helper_test_mat_to_sign(
            modes_proj, modes_proj_true[:, mode_indices], rtol=rtol,
            atol=atol)
        self._helper_test_mat_to_sign(
            np.mat(spectral_coeffs), np.mat(spectral_coeffs_true),
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            eigvals, eigvals_true, rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            np.abs(R_low_order_eigvecs / R_low_order_eigvecs_true),
            np.ones(R_low_order_eigvecs.shape),
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            np.abs(L_low_order_eigvecs / L_low_order_eigvecs_true),
            np.ones(L_low_order_eigvecs.shape),
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            correlation_mat_eigvals, correlation_mat_eigvals_true,
            rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            correlation_mat_eigvecs, correlation_mat_eigvecs_true,
            rtol=rtol, atol=atol)
        if method_type == 'snaps':
            np.testing.assert_allclose(
                correlation_mat, correlation_mat_true, rtol=rtol, atol=atol)
            np.testing.assert_allclose(
                cross_correlation_mat, cross_correlation_mat_true,
                rtol=rtol, atol=atol)


    def test_all(self):
        rtol = 1e-7
        atol = 1e-15
        mode_indices = [2, 0, 3]

        # Generate weight matrices for inner products, which should all be
        # positive semidefinite.
        weights_full = np.mat(
            np.random.random((self.num_states, self.num_states)))
        weights_full = 0.5 * (weights_full + weights_full.T)
        weights_full = weights_full + self.num_states * np.eye(self.num_states)
        weights_diag = np.random.random(self.num_states)
        weights_list = [None, weights_diag, weights_full]
        for weights in weights_list:
            IP = VectorSpaceMatrices(weights=weights).compute_inner_product_mat
            vecs = np.random.random((self.num_states, self.num_vecs))

            # Test DMD for a sequential dataset, method of snapshots
            self._helper_check_decomp(
                'snaps', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=None)

            # Check that truncation works
            max_num_eigvals = int(np.round(self.num_vecs / 2))
            self._helper_check_decomp(
                'snaps', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=None, max_num_eigvals=max_num_eigvals)

            # Test DMD for a sequential dataset, direct method
            self._helper_check_decomp(
                'direct', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=None)

            # Check that truncation works
            self._helper_check_decomp(
                'direct', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=None, max_num_eigvals=max_num_eigvals)

            # Generate data for a non-sequential dataset
            adv_vecs = np.random.random((self.num_states, self.num_vecs))

            # Test DMD for a non-sequential dataset, method of snapshots
            self._helper_check_decomp(
                'snaps', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=adv_vecs)

            # Check that truncation works
            self._helper_check_decomp(
                'snaps', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=adv_vecs, max_num_eigvals=max_num_eigvals)

            # Test DMD for a non-sequential dataset, direct method
            self._helper_check_decomp(
                'direct', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=adv_vecs)

            # Check that truncation works
            self._helper_check_decomp(
                'direct', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=adv_vecs, max_num_eigvals=max_num_eigvals)


#@unittest.skip('Testing something else.')
class TestDMDHandles(unittest.TestCase):
    def setUp(self):
        if not os.access('.', os.W_OK):
            raise RuntimeError('Cannot write to current directory')
        self.test_dir = 'DELETE_ME_test_files_dmd'
        if not os.path.isdir(self.test_dir) and parallel.is_rank_zero():
            os.mkdir(self.test_dir)

        self.num_vecs = 10
        self.num_states = 20
        self.my_DMD = DMDHandles(np.vdot, verbosity=0)

        self.vec_path = join(self.test_dir, 'dmd_vec_%03d.pkl')
        self.adv_vec_path = join(self.test_dir, 'dmd_adv_vec_%03d.pkl')
        self.mode_path = join(self.test_dir, 'dmd_truemode_%03d.pkl')
        self.vec_handles = [V.VecHandlePickle(self.vec_path%i)
            for i in range(self.num_vecs)]
        self.adv_vec_handles = [
            V.VecHandlePickle(self.adv_vec_path%i)
            for i in range(self.num_vecs)]
        parallel.barrier()


    def tearDown(self):
        parallel.barrier()
        if parallel.is_rank_zero():
            rmtree(self.test_dir, ignore_errors=True)
        parallel.barrier()


    #@unittest.skip('Testing something else.')
    def test_init(self):
        """Test arguments passed to the constructor are assigned properly"""
        # Get default data member values
        # Set verbosity to false, to avoid printing warnings during tests
        def my_load(fname): pass
        def my_save(data, fname): pass
        def my_IP(vec1, vec2): pass

        data_members_default = {
            'put_mat': util.save_array_text, 'get_mat': util.load_array_text,
            'verbosity': 0, 'eigvals': None, 'correlation_mat': None,
            'cross_correlation_mat': None, 'correlation_mat_eigvals': None,
            'correlation_mat_eigvecs': None, 'low_order_linear_map': None,
            'L_low_order_eigvecs': None, 'R_low_order_eigvecs': None,
            'spectral_coeffs': None, 'proj_coeffs': None, 'adv_proj_coeffs':
            None, 'vec_handles': None, 'adv_vec_handles': None, 'vec_space':
            VectorSpaceHandles(my_IP, verbosity=0)}

        # Get default data member values
        for k,v in util.get_data_members(
            DMDHandles(my_IP, verbosity=0)).items():
            self.assertEqual(v, data_members_default[k])

        my_DMD = DMDHandles(my_IP, verbosity=0)
        data_members_modified = copy.deepcopy(data_members_default)
        data_members_modified['vec_space'] = VectorSpaceHandles(
            inner_product=my_IP, verbosity=0)
        for k,v in util.get_data_members(my_DMD).items():
            self.assertEqual(v, data_members_modified[k])

        my_DMD = DMDHandles(my_IP, get_mat=my_load, verbosity=0)
        data_members_modified = copy.deepcopy(data_members_default)
        data_members_modified['get_mat'] = my_load
        for k,v in util.get_data_members(my_DMD).items():
            self.assertEqual(v, data_members_modified[k])

        my_DMD = DMDHandles(my_IP, put_mat=my_save, verbosity=0)
        data_members_modified = copy.deepcopy(data_members_default)
        data_members_modified['put_mat'] = my_save
        for k,v in util.get_data_members(my_DMD).items():
            self.assertEqual(v, data_members_modified[k])

        max_vecs_per_node = 500
        my_DMD = DMDHandles(my_IP, max_vecs_per_node=max_vecs_per_node,
            verbosity=0)
        data_members_modified = copy.deepcopy(data_members_default)
        data_members_modified['vec_space'].max_vecs_per_node = \
            max_vecs_per_node
        data_members_modified['vec_space'].max_vecs_per_proc = \
            max_vecs_per_node * parallel.get_num_nodes() / \
            parallel.get_num_procs()
        for k,v in util.get_data_members(my_DMD).items():
            self.assertEqual(v, data_members_modified[k])


    #@unittest.skip('Testing something else.')
    def test_puts_gets(self):
        """Test get and put functions"""
        if not os.access('.', os.W_OK):
            raise RuntimeError('Cannot write to current directory')
        test_dir = 'DELETE_ME_test_files_dmd'
        if not os.path.isdir(test_dir) and parallel.is_rank_zero():
            os.mkdir(test_dir)
        eigvals = parallel.call_and_bcast(np.random.random, 5)
        R_low_order_eigvecs = parallel.call_and_bcast(
            np.random.random, (10,10))
        L_low_order_eigvecs = parallel.call_and_bcast(
            np.random.random, (10,10))
        correlation_mat_eigvals = parallel.call_and_bcast(np.random.random, 5)
        correlation_mat_eigvecs = parallel.call_and_bcast(
            np.random.random, (10,10))
        correlation_mat = parallel.call_and_bcast(np.random.random, (10,10))
        cross_correlation_mat = parallel.call_and_bcast(
            np.random.random, (10,10))
        spectral_coeffs = parallel.call_and_bcast(np.random.random, 5)
        proj_coeffs = parallel.call_and_bcast(np.random.random, 5)
        adv_proj_coeffs = parallel.call_and_bcast(np.random.random, 5)

        my_DMD = DMDHandles(None, verbosity=0)
        my_DMD.eigvals = eigvals
        my_DMD.R_low_order_eigvecs = R_low_order_eigvecs
        my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        my_DMD.correlation_mat_eigvals = correlation_mat_eigvals
        my_DMD.correlation_mat_eigvecs = correlation_mat_eigvecs
        my_DMD.correlation_mat = correlation_mat
        my_DMD.cross_correlation_mat = cross_correlation_mat
        my_DMD.spectral_coeffs = spectral_coeffs
        my_DMD.proj_coeffs = proj_coeffs
        my_DMD.adv_proj_coeffs = adv_proj_coeffs

        eigvals_path = join(test_dir, 'dmd_eigvals.txt')
        R_low_order_eigvecs_path = join(
            test_dir, 'dmd_R_low_order_eigvecs.txt')
        L_low_order_eigvecs_path = join(
            test_dir, 'dmd_L_low_order_eigvecs.txt')
        correlation_mat_eigvals_path = join(
            test_dir, 'dmd_corr_mat_eigvals.txt')
        correlation_mat_eigvecs_path = join(
            test_dir, 'dmd_corr_mat_eigvecs.txt')
        correlation_mat_path = join(test_dir, 'dmd_corr_mat.txt')
        cross_correlation_mat_path = join(test_dir, 'dmd_cross_corr_mat.txt')
        spectral_coeffs_path = join(test_dir, 'dmd_spectral_coeffs.txt')
        proj_coeffs_path = join(test_dir, 'dmd_proj_coeffs.txt')
        adv_proj_coeffs_path = join(test_dir, 'dmd_adv_proj_coeffs.txt')

        my_DMD.put_decomp(
            eigvals_path, R_low_order_eigvecs_path, L_low_order_eigvecs_path,
            correlation_mat_eigvals_path , correlation_mat_eigvecs_path)
        my_DMD.put_correlation_mat(correlation_mat_path)
        my_DMD.put_cross_correlation_mat(cross_correlation_mat_path)
        my_DMD.put_spectral_coeffs(spectral_coeffs_path)
        my_DMD.put_proj_coeffs(proj_coeffs_path, adv_proj_coeffs_path)
        parallel.barrier()

        DMD_load = DMDHandles(None, verbosity=0)
        DMD_load.get_decomp(
            eigvals_path, R_low_order_eigvecs_path, L_low_order_eigvecs_path,
            correlation_mat_eigvals_path, correlation_mat_eigvecs_path)
        correlation_mat_loaded = util.load_array_text(correlation_mat_path)
        cross_correlation_mat_loaded = util.load_array_text(
            cross_correlation_mat_path)
        spectral_coeffs_loaded = np.squeeze(np.array(
            util.load_array_text(spectral_coeffs_path)))
        proj_coeffs_loaded = np.squeeze(np.array(
            util.load_array_text(proj_coeffs_path)))
        adv_proj_coeffs_loaded = np.squeeze(np.array(
            util.load_array_text(adv_proj_coeffs_path)))

        np.testing.assert_allclose(DMD_load.eigvals, eigvals)
        np.testing.assert_allclose(
            DMD_load.R_low_order_eigvecs, R_low_order_eigvecs)
        np.testing.assert_allclose(
            DMD_load.L_low_order_eigvecs, L_low_order_eigvecs)
        np.testing.assert_allclose(
            DMD_load.correlation_mat_eigvals, correlation_mat_eigvals)
        np.testing.assert_allclose(
            DMD_load.correlation_mat_eigvecs, correlation_mat_eigvecs)
        np.testing.assert_allclose(correlation_mat_loaded, correlation_mat)
        np.testing.assert_allclose(
            cross_correlation_mat_loaded, cross_correlation_mat)
        np.testing.assert_allclose(spectral_coeffs_loaded, spectral_coeffs)
        np.testing.assert_allclose(proj_coeffs_loaded, proj_coeffs)
        np.testing.assert_allclose(adv_proj_coeffs_loaded, adv_proj_coeffs)


    def _helper_compute_DMD_from_data(
        self, vec_array, inner_product, adv_vec_array=None,
        max_num_eigvals=None):
        # Generate adv_vec_array for the case of a sequential dataset
        if adv_vec_array is None:
            adv_vec_array = vec_array[:, 1:]
            vec_array = vec_array[:, :-1]

        # Create lists of vecs, advanced vecs for inner product function
        vecs = [vec_array[:, i] for i in range(vec_array.shape[1])]
        adv_vecs = [adv_vec_array[:, i] for i in range(adv_vec_array.shape[1])]

        # Compute SVD of data vectors
        correlation_mat = inner_product(vecs, vecs)
        correlation_mat_eigvals, correlation_mat_eigvecs = util.eigh(
            correlation_mat)
        cross_correlation_mat = inner_product(vecs, adv_vecs)
        U = vec_array.dot(np.array(correlation_mat_eigvecs)).dot(
            np.diag(correlation_mat_eigvals ** -0.5))
        U_list = [U[:, i] for i in range(U.shape[1])]

        # Truncate SVD if necessary
        if max_num_eigvals is not None and (
            max_num_eigvals < correlation_mat_eigvals.size):
            correlation_mat_eigvals = correlation_mat_eigvals[:max_num_eigvals]
            correlation_mat_eigvecs = correlation_mat_eigvecs[
                :, :max_num_eigvals]
            U = U[:, :max_num_eigvals]
            U_list = U_list[:max_num_eigvals]

        # Compute eigendecomposition of low order linear operator
        A_tilde = inner_product(U_list, adv_vecs).dot(
            np.array(correlation_mat_eigvecs)).dot(
            np.diag(correlation_mat_eigvals ** -0.5))
        eigvals, R_low_order_eigvecs, L_low_order_eigvecs =\
            util.eig_biorthog(A_tilde, scale_choice='left')
        R_low_order_eigvecs = np.mat(R_low_order_eigvecs)
        L_low_order_eigvecs = np.mat(L_low_order_eigvecs)

        # Compute build coefficients
        build_coeffs_proj = (
            correlation_mat_eigvecs.dot(
            np.diag(correlation_mat_eigvals ** -0.5)).dot(R_low_order_eigvecs))
        build_coeffs_exact = (
            correlation_mat_eigvecs.dot(
            np.diag(correlation_mat_eigvals ** -0.5)).dot(
            R_low_order_eigvecs).dot(
            np.diag(eigvals ** -1.)))

        # Compute modes
        modes_proj = vec_array.dot(build_coeffs_proj)
        modes_exact = adv_vec_array.dot(build_coeffs_exact)
        adj_modes = U.dot(L_low_order_eigvecs)
        adj_modes_list = [
            np.array(adj_modes[:, i]) for i in range(adj_modes.shape[1])]

        return (
            modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
            L_low_order_eigvecs, correlation_mat_eigvals,
            correlation_mat_eigvecs, cross_correlation_mat, adj_modes)


    def _helper_test_1D_array_to_sign(
        self, true_vals, test_vals, rtol=1e-12, atol=1e-16):
        # Check that shapes are the same
        self.assertEqual(len(true_vals.shape), 1)
        self.assertEqual(len(test_vals.shape), 1)
        self.assertEqual(true_vals.size, test_vals.size)

        # Check values entry by entry.
        for idx in range(true_vals.size):
            true_val = true_vals[idx]
            test_val = test_vals[idx]
            self.assertTrue(
                np.allclose(true_val, test_val, rtol=rtol, atol=atol)
                or
                np.allclose(-true_val, test_val, rtol=rtol, atol=atol))


    def _helper_test_mat_to_sign(
        self, true_vals, test_vals, rtol=1e-12, atol=1e-16):
        # Check that shapes are the same
        self.assertEqual(len(true_vals.shape), len(test_vals.shape))
        for shape_idx in range(len(true_vals.shape)):
            self.assertEqual(
                true_vals.shape[shape_idx], test_vals.shape[shape_idx])

        # Check values column by columns.  To allow for matrices or arrays,
        # turn columns into arrays and squeeze them (forcing 1D arrays).  This
        # avoids failures due to trivial shape mismatches.
        for col_idx in range(true_vals.shape[1]):
            true_col = np.array(true_vals[:, col_idx]).squeeze()
            test_col = np.array(test_vals[:, col_idx]).squeeze()
            self.assertTrue(
                np.allclose(true_col, test_col, rtol=rtol, atol=atol)
                or
                np.allclose(-true_col, test_col, rtol=rtol, atol=atol))


    def _helper_check_decomp(
        self, vec_array,  vec_handles, adv_vec_array=None,
        adv_vec_handles=None, max_num_eigvals=None):
        # Set tolerance
        rtol = 1e-10
        atol = 1e-12

        # Compute reference DMD values
        (eigvals_true, R_low_order_eigvecs_true, L_low_order_eigvecs_true,
            correlation_mat_eigvals_true, correlation_mat_eigvecs_true) = (
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            adv_vec_array=adv_vec_array,
            max_num_eigvals=max_num_eigvals))[2:-2]

        # Compute DMD using modred
        (eigvals_returned,  R_low_order_eigvecs_returned,
            L_low_order_eigvecs_returned, correlation_mat_eigvals_returned,
            correlation_mat_eigvecs_returned) = self.my_DMD.compute_decomp(
            vec_handles, adv_vec_handles=adv_vec_handles,
            max_num_eigvals=max_num_eigvals)

        # Test that matrices were correctly computed.  For build coeffs, check
        # column by column, as it is ok to be off by a negative sign.
        np.testing.assert_allclose(
            self.my_DMD.eigvals, eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            self.my_DMD.R_low_order_eigvecs, R_low_order_eigvecs_true,
            rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            self.my_DMD.L_low_order_eigvecs, L_low_order_eigvecs_true,
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            self.my_DMD.correlation_mat_eigvals, correlation_mat_eigvals_true,
            rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            self.my_DMD.correlation_mat_eigvecs, correlation_mat_eigvecs_true,
            rtol=rtol, atol=atol)

        # Test that matrices were correctly returned
        np.testing.assert_allclose(
            eigvals_returned, eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            R_low_order_eigvecs_returned, R_low_order_eigvecs_true, rtol=rtol,
            atol=atol)
        self._helper_test_mat_to_sign(
            L_low_order_eigvecs_returned, L_low_order_eigvecs_true, rtol=rtol,
            atol=atol)
        np.testing.assert_allclose(
            correlation_mat_eigvals_returned, correlation_mat_eigvals_true,
            rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            correlation_mat_eigvecs_returned, correlation_mat_eigvecs_true,
            rtol=rtol, atol=atol)


    def _helper_check_modes(self, modes_true, mode_path_list):
        # Set tolerance
        rtol = 1e-10
        atol = 1e-12

        # Load all modes into matrix, compare to modes from direct computation
        modes_computed = np.zeros(modes_true.shape, dtype=complex)
        for i, path in enumerate(mode_path_list):
            modes_computed[:, i] = V.VecHandlePickle(path).get()
        np.testing.assert_allclose(
            modes_true, modes_computed, rtol=rtol, atol=atol)


    #@unittest.skip('Testing something else.')
    def test_compute_decomp(self):
        """Test DMD decomposition"""
        # Define an array of vectors, with corresponding handles
        vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.vec_handles):
                handle.put(np.array(vec_array[:, vec_index]).squeeze())

        # Check modred against direct computation, for a sequential dataset
        parallel.barrier()
        self._helper_check_decomp(vec_array, self.vec_handles)

        # Make sure truncation works
        max_num_eigvals = int(np.round(self.num_vecs / 2))
        self._helper_check_decomp(vec_array, self.vec_handles,
            max_num_eigvals=max_num_eigvals)

        # Create more data, to check a non-sequential dataset
        adv_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.adv_vec_handles):
                handle.put(np.array(adv_vec_array[:, vec_index]).squeeze())

        # Check modred against direct computation, for a non-sequential dataset
        parallel.barrier()
        self._helper_check_decomp(
            vec_array, self.vec_handles, adv_vec_array=adv_vec_array,
            adv_vec_handles=self.adv_vec_handles)

        # Make sure truncation works
        self._helper_check_decomp(
            vec_array, self.vec_handles, adv_vec_array=adv_vec_array,
            adv_vec_handles=self.adv_vec_handles,
            max_num_eigvals=max_num_eigvals)

        # Check that if mismatched sets of handles are passed in, an error is
        # raised.
        self.assertRaises(ValueError, self.my_DMD.compute_decomp,
            self.vec_handles, self.adv_vec_handles[:-1])


    #@unittest.skip('Testing something else.')
    def test_compute_modes(self):
        """Test building of modes."""
        # Generate path names for saving modes to disk
        mode_path = join(self.test_dir, 'dmd_mode_%03d.pkl')

        ### SEQUENTIAL DATASET ###
        # Generate data
        seq_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.vec_handles):
                handle.put(np.array(seq_vec_array[:, vec_index]).squeeze())

        # Compute DMD directly from data
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, correlation_mat_eigvals,
        correlation_mat_eigvecs) = self._helper_compute_DMD_from_data(
            seq_vec_array, util.InnerProductBlock(np.vdot))[:-2]

        # Set the build_coeffs attribute of an empty DMD object each time, so
        # that the modred computation uses the same coefficients as the direct
        # computation.
        parallel.barrier()
        self.my_DMD.eigvals = eigvals
        self.my_DMD.R_low_order_eigvecs = R_low_order_eigvecs
        self.my_DMD.correlation_mat_eigvals = correlation_mat_eigvals
        self.my_DMD.correlation_mat_eigvecs = correlation_mat_eigvecs

        # Generate mode paths for saving modes to disk
        seq_mode_path_list = [
            mode_path % i for i in range(eigvals.size)]
        seq_mode_indices = range(len(seq_mode_path_list))

        # Compute modes by passing in handles
        self.my_DMD.compute_exact_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list],
            adv_vec_handles=self.vec_handles[1:])
        self._helper_check_modes(modes_exact, seq_mode_path_list)
        self.my_DMD.compute_proj_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list],
            vec_handles=self.vec_handles)
        self._helper_check_modes(modes_proj, seq_mode_path_list)

        # Compute modes without passing in handles, so first set full
        # sequential dataset as vec_handles.
        self.my_DMD.vec_handles = self.vec_handles
        self.my_DMD.compute_exact_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list])
        self._helper_check_modes(modes_exact, seq_mode_path_list)
        self.my_DMD.compute_proj_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list])
        self._helper_check_modes(modes_proj, seq_mode_path_list)

        # For exact modes, also compute by setting adv_vec_handles
        self.my_DMD.vec_handles = None
        self.my_DMD.adv_vec_handles = self.vec_handles[1:]
        self.my_DMD.compute_exact_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list])
        self._helper_check_modes(modes_exact, seq_mode_path_list)

        ### NONSEQUENTIAL DATA ###
        # Generate data
        vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        adv_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, (handle, adv_handle) in enumerate(
                zip(self.vec_handles, self.adv_vec_handles)):
                handle.put(np.array(vec_array[:, vec_index]).squeeze())
                adv_handle.put(np.array(adv_vec_array[:, vec_index]).squeeze())

        # Compute DMD directly from data
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, correlation_mat_eigvals,
        correlation_mat_eigvecs) = self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            adv_vec_array=adv_vec_array)[:-2]

        # Set the build_coeffs attribute of an empty DMD object each time, so
        # that the modred computation uses the same coefficients as the direct
        # computation.
        parallel.barrier()
        self.my_DMD.eigvals = eigvals
        self.my_DMD.R_low_order_eigvecs = R_low_order_eigvecs
        self.my_DMD.correlation_mat_eigvals = correlation_mat_eigvals
        self.my_DMD.correlation_mat_eigvecs = correlation_mat_eigvecs

        # Generate mode paths for saving modes to disk
        mode_path_list = [
            mode_path % i for i in range(eigvals.size)]
        mode_indices = range(len(mode_path_list))

        # Compute modes by passing in handles
        self.my_DMD.compute_exact_modes(mode_indices,
            [V.VecHandlePickle(path) for path in mode_path_list],
            adv_vec_handles=self.adv_vec_handles)
        self._helper_check_modes(modes_exact, mode_path_list)
        self.my_DMD.compute_proj_modes(mode_indices,
            [V.VecHandlePickle(path) for path in mode_path_list],
            vec_handles=self.vec_handles)
        self._helper_check_modes(modes_proj, mode_path_list)

        # Compute modes without passing in handles, so first set full
        # sequential dataset as vec_handles.
        self.my_DMD.vec_handles = self.vec_handles
        self.my_DMD.adv_vec_handles = self.adv_vec_handles
        self.my_DMD.compute_exact_modes(mode_indices,
            [V.VecHandlePickle(path) for path in mode_path_list])
        self._helper_check_modes(modes_exact, mode_path_list)
        self.my_DMD.compute_proj_modes(mode_indices,
            [V.VecHandlePickle(path) for path in mode_path_list])
        self._helper_check_modes(modes_proj, mode_path_list)


    #@unittest.skip('Testing something else.')
    def test_compute_spectrum(self):
        """Test DMD spectrum"""
        rtol = 1e-10
        atol = 1e-12

        # Define an array of vectors, with corresponding handles
        vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.vec_handles):
                handle.put(np.array(vec_array[:, vec_index]).squeeze())

        # Compute DMD manually and then set the data in a DMDHandles object.
        # This way, we test only the task of computing the spectral
        # coefficients, and not also the task of computing the decomposition.
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, correlation_mat_eigvals,
        correlation_mat_eigvecs, cross_correlation_mat, adj_modes) =\
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot))
        self.my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        self.my_DMD.correlation_mat_eigvals = correlation_mat_eigvals
        self.my_DMD.correlation_mat_eigvecs = correlation_mat_eigvecs

        # Check that spectral coefficients computed using adjoints match those
        # computed using a projection onto the adjoint modes.
        parallel.barrier()
        spectral_coeffs = self.my_DMD.compute_spectrum()
        spectral_coeffs_true = np.abs(np.array(
            np.dot(adj_modes.conj().T, vec_array[:, 0])).squeeze())
        np.testing.assert_allclose(
            spectral_coeffs, spectral_coeffs_true, rtol=rtol, atol=atol)

        # Create more data, to check a non-sequential dataset
        adv_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.adv_vec_handles):
                handle.put(np.array(adv_vec_array[:, vec_index]).squeeze())

        # Compute DMD manually and then set the data in a DMDHandles object.
        # This way, we test only the task of computing the spectral
        # coefficients, and not also the task of computing the decomposition.
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, correlation_mat_eigvals,
        correlation_mat_eigvecs, cross_correlation_mat, adj_modes) =\
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            adv_vec_array=adv_vec_array)
        self.my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        self.my_DMD.correlation_mat_eigvals = correlation_mat_eigvals
        self.my_DMD.correlation_mat_eigvecs = correlation_mat_eigvecs

        # Check that spectral coefficients computed using adjoints match those
        # computed using a direct projection onto the adjoint modes
        parallel.barrier()
        spectral_coeffs = self.my_DMD.compute_spectrum()
        spectral_coeffs_true = np.abs(np.array(
            np.dot(adj_modes.conj().T, vec_array[:, 0])).squeeze())
        np.testing.assert_allclose(
            spectral_coeffs, spectral_coeffs_true, rtol=rtol, atol=atol)


    #@unittest.skip('Testing something else.')
    def test_compute_proj_coeffs(self):
        """Test projection coefficients"""
        rtol = 1e-10
        atol = 1e-12

        # Define an array of vectors, with corresponding handles
        vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.vec_handles):
                handle.put(np.array(vec_array[:, vec_index]).squeeze())

        # Compute DMD manually and then set the data in a DMDHandles object.
        # This way, we test only the task of computing the projection
        # coefficients, and not also the task of computing the decomposition.
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, correlation_mat_eigvals,
        correlation_mat_eigvecs, cross_correlation_mat, adj_modes) =\
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot))
        self.my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        self.my_DMD.correlation_mat_eigvals = correlation_mat_eigvals
        self.my_DMD.correlation_mat_eigvecs = correlation_mat_eigvecs
        self.my_DMD.cross_correlation_mat = cross_correlation_mat

        # Check the spectral coefficient values.  Compare the formula
        # implemented in modred to a direct projection onto the adjoint modes.
        parallel.barrier()
        proj_coeffs, adv_proj_coeffs = self.my_DMD.compute_proj_coeffs()
        proj_coeffs_true = np.dot(adj_modes.conj().T, vec_array[:, :-1])
        adv_proj_coeffs_true = np.dot(adj_modes.conj().T, vec_array[:, 1:])
        np.testing.assert_allclose(
            proj_coeffs, proj_coeffs_true,
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            adv_proj_coeffs, adv_proj_coeffs_true, rtol=rtol, atol=atol)

        # Create more data, to check a non-sequential dataset
        adv_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.adv_vec_handles):
                handle.put(np.array(adv_vec_array[:, vec_index]).squeeze())

        # Compute DMD manually and then set the data in a DMDHandles object.
        # This way, we test only the task of computing the projection
        # coefficients, and not also the task of computing the decomposition.
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, correlation_mat_eigvals,
        correlation_mat_eigvecs, cross_correlation_mat, adj_modes) =\
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            adv_vec_array=adv_vec_array)
        self.my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        self.my_DMD.correlation_mat_eigvals = correlation_mat_eigvals
        self.my_DMD.correlation_mat_eigvecs = correlation_mat_eigvecs
        self.my_DMD.cross_correlation_mat = cross_correlation_mat

        # Check the spectral coefficient values.  Compare the formula
        # implemented in modred to a direct projection onto the adjoint modes.
        parallel.barrier()
        proj_coeffs, adv_proj_coeffs= self.my_DMD.compute_proj_coeffs()
        proj_coeffs_true = np.dot(adj_modes.conj().T, vec_array)
        adv_proj_coeffs_true = np.dot(adj_modes.conj().T, adv_vec_array)
        np.testing.assert_allclose(
            proj_coeffs, proj_coeffs_true, rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            adv_proj_coeffs, adv_proj_coeffs_true, rtol=rtol, atol=atol)


#@unittest.skip('Testing something else.')
@unittest.skipIf(parallel.is_distributed(), 'Serial only.')
class TestTLSqrDMDArraysFunctions(unittest.TestCase):
    def setUp(self):
        # Generate vecs if we are on the first processor
        # A random matrix of data (#cols = #vecs)
        self.num_vecs = 30
        self.num_states = 10
        self.max_num_eigvals = int(np.round(self.num_states / 2))


    def _helper_compute_DMD_from_data(
        self, vecs, inner_product, adv_vecs=None, max_num_eigvals=None):
        if adv_vecs is None:
            adv_vecs = vecs[:, 1:]
            vecs = vecs[:, :-1]

        # Inner products
        correlation_mat = inner_product(vecs, vecs)
        cross_correlation_mat = inner_product(vecs, adv_vecs)
        adv_correlation_mat = inner_product(adv_vecs, adv_vecs)
        summed_correlation_mats = correlation_mat + adv_correlation_mat

        # SVD of stacked data vectors
        stacked_V, stacked_Sigma, dummy = util.svd(summed_correlation_mats)
        stacked_U = vecs.dot(stacked_V).dot(np.diag(stacked_Sigma ** -0.5))

        # Truncate if necessary
        if max_num_eigvals is not None and (
            max_num_eigvals < stacked_Sigma.size):
            stacked_V = stacked_V[:, :max_num_eigvals]
            stacked_Sigma = stacked_Sigma[:max_num_eigvals]
            stacked_U = stacked_U[:, :max_num_eigvals]

        # Project data
        vecs_proj = np.mat(vecs) * stacked_V * stacked_V.T
        adv_vecs_proj = np.mat(adv_vecs) * stacked_V * stacked_V.T

        # SVD of projected data
        proj_correlation_mat = inner_product(vecs_proj, vecs_proj)
        proj_V, proj_Sigma, dummy = util.svd(proj_correlation_mat)
        proj_U = vecs_proj.dot(proj_V).dot(np.diag(proj_Sigma ** -0.5))

        # Truncate if necessary
        if max_num_eigvals is not None and (
            max_num_eigvals < proj_Sigma.size):
            proj_V = proj_V[:, :max_num_eigvals]
            proj_Sigma = proj_Sigma[:max_num_eigvals]
            proj_U = proj_U[:, :max_num_eigvals]

        A_tilde = inner_product(
            proj_U, adv_vecs_proj).dot(proj_V).dot(np.diag(proj_Sigma ** -0.5))
        eigvals, W, Z = util.eig_biorthog(A_tilde, scale_choice='left')
        build_coeffs_proj = proj_V.dot(np.diag(proj_Sigma ** -0.5)).dot(W)
        build_coeffs_exact = (
            proj_V.dot(np.diag(proj_Sigma ** -0.5)).dot(W).dot(
            np.diag(eigvals ** -1.)))
        modes_proj = vecs_proj.dot(build_coeffs_proj)
        modes_exact = adv_vecs_proj.dot(build_coeffs_exact)
        adj_modes = proj_U.dot(Z)
        spectral_coeffs = np.abs(np.array(
            inner_product(adj_modes, np.mat(vecs_proj[:, 0]))).squeeze())

        return (
            modes_exact, modes_proj, spectral_coeffs, eigvals,
            W, Z, stacked_Sigma, stacked_V, proj_Sigma, proj_V,
            correlation_mat, adv_correlation_mat, cross_correlation_mat)


    def _helper_test_mat_to_sign(
        self, true_vals, test_vals, rtol=1e-12, atol=1e-16):
        # Check that shapes are the same
        self.assertEqual(len(true_vals.shape), len(test_vals.shape))
        for shape_idx in range(len(true_vals.shape)):
            self.assertEqual(
                true_vals.shape[shape_idx], test_vals.shape[shape_idx])

        # Check values column by columns.  To allow for matrices or arrays,
        # turn columns into arrays and squeeze them (forcing 1D arrays).  This
        # avoids failures due to trivial shape mismatches.
        for col_idx in range(true_vals.shape[1]):
            true_col = np.array(true_vals[:, col_idx]).squeeze()
            test_col = np.array(test_vals[:, col_idx]).squeeze()
            self.assertTrue(
                np.allclose(true_col, test_col, rtol=rtol, atol=atol)
                or
                np.allclose(-true_col, test_col, rtol=rtol, atol=atol))


    def _helper_check_decomp(
        self, method_type, vecs, mode_indices, inner_product,
        inner_product_weights, rtol, atol, adv_vecs=None,
        max_num_eigvals=None):

        # Compute reference values for testing DMD computation
        (modes_exact_true, modes_proj_true, spectral_coeffs_true,
            eigvals_true, R_low_order_eigvecs_true, L_low_order_eigvecs_true,
            summed_correlation_mats_eigvals_true,
            summed_correlation_mats_eigvecs_true,
            proj_correlation_mat_eigvals_true,
            proj_correlation_mat_eigvecs_true,
            correlation_mat_true, adv_correlation_mat_true,
            cross_correlation_mat_true) = (
            self._helper_compute_DMD_from_data(
            vecs, inner_product, adv_vecs=adv_vecs,
            max_num_eigvals=max_num_eigvals))

        # Compute DMD using modred method of choice
        if method_type == 'snaps':
            (modes_exact, modes_proj, spectral_coeffs, eigvals,
                R_low_order_eigvecs, L_low_order_eigvecs,
                summed_correlation_mats_eigvals,
                summed_correlation_mats_eigvecs,
                proj_correlation_mat_eigvals, proj_correlation_mat_eigvecs,
                correlation_mat, adv_correlation_mat, cross_correlation_mat) =\
                compute_TLSqrDMD_matrices_snaps_method(
                vecs, mode_indices, adv_vecs=adv_vecs,
                inner_product_weights=inner_product_weights,
                max_num_eigvals=max_num_eigvals, return_all=True)
        elif method_type == 'direct':
            (modes_exact, modes_proj, spectral_coeffs, eigvals,
                R_low_order_eigvecs, L_low_order_eigvecs,
                summed_correlation_mats_eigvals,
                summed_correlation_mats_eigvecs,
                proj_correlation_mat_eigvals, proj_correlation_mat_eigvecs) =\
                compute_TLSqrDMD_matrices_direct_method(
                vecs, mode_indices, adv_vecs=adv_vecs,
                inner_product_weights=inner_product_weights,
                max_num_eigvals=max_num_eigvals, return_all=True)
        else:
            raise ValueError('Invalid DMD matrix method.')

        # Compare values to reference values, allowing for sign differences in
        # some cases.  For the low-order eigenvectors, check that the elements
        # differ at most by a sign, as the eigenvectors may vary by sign even
        # element-wise.  This is due to the fact that the low-order linear maps
        # may have sign differences, as they depend on the correlation matrix
        # eigenvectors, which themselves may have column-wise sign differences.
        self._helper_test_mat_to_sign(
            modes_exact, modes_exact_true[:, mode_indices], rtol=rtol,
            atol=atol)
        self._helper_test_mat_to_sign(
            modes_proj, modes_proj_true[:, mode_indices], rtol=rtol,
            atol=atol)
        self._helper_test_mat_to_sign(
            np.mat(spectral_coeffs), np.mat(spectral_coeffs_true),
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            eigvals, eigvals_true, rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            np.abs(R_low_order_eigvecs / R_low_order_eigvecs_true),
            np.ones(R_low_order_eigvecs.shape),
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            np.abs(L_low_order_eigvecs / L_low_order_eigvecs_true),
            np.ones(L_low_order_eigvecs.shape),
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            summed_correlation_mats_eigvals,
            summed_correlation_mats_eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            summed_correlation_mats_eigvecs,
            summed_correlation_mats_eigvecs_true, rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            proj_correlation_mat_eigvals, proj_correlation_mat_eigvals_true,
            rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            proj_correlation_mat_eigvecs, proj_correlation_mat_eigvecs_true,
            rtol=rtol, atol=atol)
        if method_type == 'snaps':
            np.testing.assert_allclose(
                correlation_mat, correlation_mat_true, rtol=rtol, atol=atol)
            np.testing.assert_allclose(
                adv_correlation_mat, adv_correlation_mat_true, rtol=rtol,
                atol=atol)
            np.testing.assert_allclose(
                cross_correlation_mat, cross_correlation_mat_true,
                rtol=rtol, atol=atol)


    def test_all(self):
        rtol = 1e-7
        atol = 1e-15
        mode_indices = [2, 0, 3]

        # Generate weight matrices for inner products, which should all be
        # positive semidefinite.
        weights_full = np.mat(
            np.random.random((self.num_states, self.num_states)))
        weights_full = 0.5 * (weights_full + weights_full.T)
        weights_full = weights_full + self.num_states * np.eye(self.num_states)
        weights_diag = np.random.random(self.num_states)
        weights_list = [None, weights_diag, weights_full]
        for weights in weights_list:
            IP = VectorSpaceMatrices(weights=weights).compute_inner_product_mat
            vecs = np.random.random((self.num_states, self.num_vecs))

            # Test DMD for a sequential dataset, method of snapshots
            self._helper_check_decomp(
                'snaps', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=None, max_num_eigvals=self.max_num_eigvals)

            # Test DMD for a sequential dataset, direct method
            self._helper_check_decomp(
                'direct', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=None, max_num_eigvals=self.max_num_eigvals)

            # Generate data for a non-sequential dataset
            adv_vecs = np.random.random((self.num_states, self.num_vecs))

            # Test DMD for a non-sequential dataset, method of snapshots
            self._helper_check_decomp(
                'snaps', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=adv_vecs, max_num_eigvals=self.max_num_eigvals)

            # Test DMD for a non-sequential dataset, direct method
            self._helper_check_decomp(
                'direct', vecs, mode_indices, IP, weights, rtol, atol,
                adv_vecs=adv_vecs, max_num_eigvals=self.max_num_eigvals)


#@unittest.skip('others')
class TestTLSqrDMDHandles(unittest.TestCase):
    def setUp(self):
        if not os.access('.', os.W_OK):
            raise RuntimeError('Cannot write to current directory')
        self.test_dir = 'DELETE_ME_test_files_dmd'
        if not os.path.isdir(self.test_dir) and parallel.is_rank_zero():
            os.mkdir(self.test_dir)

        self.num_vecs = 10
        self.num_states = 30
        self.max_num_eigvals = int(np.round(self.num_states / 2))
        self.my_DMD = TLSqrDMDHandles(np.vdot, verbosity=0)

        self.vec_path = join(self.test_dir, 'dmd_vec_%03d.pkl')
        self.adv_vec_path = join(self.test_dir, 'dmd_adv_vec_%03d.pkl')
        self.mode_path = join(self.test_dir, 'dmd_truemode_%03d.pkl')
        self.vec_handles = [V.VecHandlePickle(self.vec_path%i)
            for i in range(self.num_vecs)]
        self.adv_vec_handles = [
            V.VecHandlePickle(self.adv_vec_path%i)
            for i in range(self.num_vecs)]
        parallel.barrier()


    def tearDown(self):
        parallel.barrier()
        if parallel.is_rank_zero():
            rmtree(self.test_dir, ignore_errors=True)
        parallel.barrier()


    #@unittest.skip('Testing something else.')
    def test_init(self):
        """Test arguments passed to the constructor are assigned properly"""
        # Get default data member values
        # Set verbosity to false, to avoid printing warnings during tests
        def my_load(fname): pass
        def my_save(data, fname): pass
        def my_IP(vec1, vec2): pass

        data_members_default = {
            'put_mat': util.save_array_text, 'get_mat': util.load_array_text,
            'verbosity': 0, 'eigvals': None, 'correlation_mat': None,
            'cross_correlation_mat': None, 'adv_correlation_mat': None,
            'summed_correlation_mats_eigvals': None,
            'summed_correlation_mats_eigvecs': None,
            'proj_correlation_mat_eigvals': None,
            'proj_correlation_mat_eigvecs': None, 'low_order_linear_map': None,
            'L_low_order_eigvecs': None, 'R_low_order_eigvecs': None,
            'spectral_coeffs': None, 'proj_coeffs': None, 'adv_proj_coeffs':
            None, 'vec_handles': None, 'adv_vec_handles': None, 'vec_space':
            VectorSpaceHandles(my_IP, verbosity=0)}

        # Get default data member values
        for k,v in util.get_data_members(
            TLSqrDMDHandles(my_IP, verbosity=0)).items():
            self.assertEqual(v, data_members_default[k])

        my_DMD = TLSqrDMDHandles(my_IP, verbosity=0)
        data_members_modified = copy.deepcopy(data_members_default)
        data_members_modified['vec_space'] = VectorSpaceHandles(
            inner_product=my_IP, verbosity=0)
        for k,v in util.get_data_members(my_DMD).items():
            self.assertEqual(v, data_members_modified[k])

        my_DMD = TLSqrDMDHandles(my_IP, get_mat=my_load, verbosity=0)
        data_members_modified = copy.deepcopy(data_members_default)
        data_members_modified['get_mat'] = my_load
        for k,v in util.get_data_members(my_DMD).items():
            self.assertEqual(v, data_members_modified[k])

        my_DMD = TLSqrDMDHandles(my_IP, put_mat=my_save, verbosity=0)
        data_members_modified = copy.deepcopy(data_members_default)
        data_members_modified['put_mat'] = my_save
        for k,v in util.get_data_members(my_DMD).items():
            self.assertEqual(v, data_members_modified[k])

        max_vecs_per_node = 500
        my_DMD = TLSqrDMDHandles(my_IP, max_vecs_per_node=max_vecs_per_node,
            verbosity=0)
        data_members_modified = copy.deepcopy(data_members_default)
        data_members_modified['vec_space'].max_vecs_per_node = \
            max_vecs_per_node
        data_members_modified['vec_space'].max_vecs_per_proc = \
            max_vecs_per_node * parallel.get_num_nodes() / \
            parallel.get_num_procs()
        for k,v in util.get_data_members(my_DMD).items():
            self.assertEqual(v, data_members_modified[k])


    #@unittest.skip('Testing something else.')
    def test_puts_gets(self):
        """Test get and put functions"""
        if not os.access('.', os.W_OK):
            raise RuntimeError('Cannot write to current directory')
        test_dir = 'DELETE_ME_test_files_dmd'
        if not os.path.isdir(test_dir) and parallel.is_rank_zero():
            os.mkdir(test_dir)
        eigvals = parallel.call_and_bcast(np.random.random, 5)
        R_low_order_eigvecs = parallel.call_and_bcast(
            np.random.random, (10,10))
        L_low_order_eigvecs = parallel.call_and_bcast(
            np.random.random, (10,10))
        summed_correlation_mats_eigvals = parallel.call_and_bcast(
            np.random.random, 5)
        summed_correlation_mats_eigvecs = parallel.call_and_bcast(
            np.random.random, (10,10))
        proj_correlation_mat_eigvals = parallel.call_and_bcast(
            np.random.random, 5)
        proj_correlation_mat_eigvecs = parallel.call_and_bcast(
            np.random.random, (10,10))
        correlation_mat = parallel.call_and_bcast(np.random.random, (10,10))
        cross_correlation_mat = parallel.call_and_bcast(
            np.random.random, (10,10))
        adv_correlation_mat = parallel.call_and_bcast(
            np.random.random, (10,10))
        spectral_coeffs = parallel.call_and_bcast(np.random.random, 5)
        proj_coeffs = parallel.call_and_bcast(np.random.random, 5)
        adv_proj_coeffs = parallel.call_and_bcast(np.random.random, 5)

        my_DMD = TLSqrDMDHandles(None, verbosity=0)
        my_DMD.eigvals = eigvals
        my_DMD.R_low_order_eigvecs = R_low_order_eigvecs
        my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        my_DMD.summed_correlation_mats_eigvals =\
            summed_correlation_mats_eigvals
        my_DMD.summed_correlation_mats_eigvecs =\
            summed_correlation_mats_eigvecs
        my_DMD.proj_correlation_mat_eigvals = proj_correlation_mat_eigvals
        my_DMD.proj_correlation_mat_eigvecs = proj_correlation_mat_eigvecs
        my_DMD.correlation_mat = correlation_mat
        my_DMD.cross_correlation_mat = cross_correlation_mat
        my_DMD.adv_correlation_mat = adv_correlation_mat
        my_DMD.spectral_coeffs = spectral_coeffs
        my_DMD.proj_coeffs = proj_coeffs
        my_DMD.adv_proj_coeffs = adv_proj_coeffs

        eigvals_path = join(test_dir, 'dmd_eigvals.txt')
        R_low_order_eigvecs_path = join(
            test_dir, 'dmd_R_low_order_eigvecs.txt')
        L_low_order_eigvecs_path = join(
            test_dir, 'dmd_L_low_order_eigvecs.txt')
        summed_correlation_mats_eigvals_path = join(
            test_dir, 'dmd_summed_corr_mats_eigvals.txt')
        summed_correlation_mats_eigvecs_path = join(
            test_dir, 'dmd_summed_corr_mats_eigvecs.txt')
        proj_correlation_mat_eigvals_path = join(
            test_dir, 'dmd_proj_corr_mat_eigvals.txt')
        proj_correlation_mat_eigvecs_path = join(
            test_dir, 'dmd_proj_corr_mat_eigvecs.txt')
        correlation_mat_path = join(test_dir, 'dmd_corr_mat.txt')
        cross_correlation_mat_path = join(test_dir, 'dmd_cross_corr_mat.txt')
        adv_correlation_mat_path = join(test_dir, 'dmd_adv_corr_mat.txt')
        spectral_coeffs_path = join(test_dir, 'dmd_spectral_coeffs.txt')
        proj_coeffs_path = join(test_dir, 'dmd_proj_coeffs.txt')
        adv_proj_coeffs_path = join(test_dir, 'dmd_adv_proj_coeffs.txt')

        my_DMD.put_decomp(
            eigvals_path, R_low_order_eigvecs_path, L_low_order_eigvecs_path,
            summed_correlation_mats_eigvals_path ,
            summed_correlation_mats_eigvecs_path,
            proj_correlation_mat_eigvals_path ,
            proj_correlation_mat_eigvecs_path)
        my_DMD.put_correlation_mat(correlation_mat_path)
        my_DMD.put_cross_correlation_mat(cross_correlation_mat_path)
        my_DMD.put_adv_correlation_mat(adv_correlation_mat_path)
        my_DMD.put_spectral_coeffs(spectral_coeffs_path)
        my_DMD.put_proj_coeffs(proj_coeffs_path, adv_proj_coeffs_path)
        parallel.barrier()

        DMD_load = TLSqrDMDHandles(None, verbosity=0)
        DMD_load.get_decomp(
            eigvals_path, R_low_order_eigvecs_path, L_low_order_eigvecs_path,
            summed_correlation_mats_eigvals_path,
            summed_correlation_mats_eigvecs_path,
            proj_correlation_mat_eigvals_path,
            proj_correlation_mat_eigvecs_path)
        correlation_mat_loaded = util.load_array_text(correlation_mat_path)
        cross_correlation_mat_loaded = util.load_array_text(
            cross_correlation_mat_path)
        adv_correlation_mat_loaded = util.load_array_text(
            adv_correlation_mat_path)
        spectral_coeffs_loaded = np.squeeze(np.array(
            util.load_array_text(spectral_coeffs_path)))
        proj_coeffs_loaded = np.squeeze(np.array(
            util.load_array_text(proj_coeffs_path)))
        adv_proj_coeffs_loaded = np.squeeze(np.array(
            util.load_array_text(adv_proj_coeffs_path)))

        np.testing.assert_allclose(DMD_load.eigvals, eigvals)
        np.testing.assert_allclose(
            DMD_load.R_low_order_eigvecs, R_low_order_eigvecs)
        np.testing.assert_allclose(
            DMD_load.L_low_order_eigvecs, L_low_order_eigvecs)
        np.testing.assert_allclose(
            DMD_load.summed_correlation_mats_eigvals,
            summed_correlation_mats_eigvals)
        np.testing.assert_allclose(
            DMD_load.summed_correlation_mats_eigvecs,
            summed_correlation_mats_eigvecs)
        np.testing.assert_allclose(
            DMD_load.proj_correlation_mat_eigvals,
            proj_correlation_mat_eigvals)
        np.testing.assert_allclose(
            DMD_load.proj_correlation_mat_eigvecs,
            proj_correlation_mat_eigvecs)
        np.testing.assert_allclose(correlation_mat_loaded, correlation_mat)
        np.testing.assert_allclose(
            cross_correlation_mat_loaded, cross_correlation_mat)
        np.testing.assert_allclose(adv_correlation_mat_loaded,
            adv_correlation_mat)
        np.testing.assert_allclose(spectral_coeffs_loaded, spectral_coeffs)
        np.testing.assert_allclose(proj_coeffs_loaded, proj_coeffs)
        np.testing.assert_allclose(adv_proj_coeffs_loaded, adv_proj_coeffs)


    def _helper_compute_DMD_from_data(
        self, vec_array, inner_product, adv_vec_array=None,
        max_num_eigvals=None):
        # Generate adv_vec_array for the case of a sequential dataset
        if adv_vec_array is None:
            adv_vec_array = vec_array[:, 1:]
            vec_array = vec_array[:, :-1]

        # Stack arrays for total-least-squares DMD
        stacked_vec_array = np.vstack((vec_array, adv_vec_array))

        # Create lists of vecs, advanced vecs for inner product function
        vecs = [vec_array[:, i] for i in range(vec_array.shape[1])]
        adv_vecs = [adv_vec_array[:, i] for i in range(adv_vec_array.shape[1])]
        stacked_vecs = [
            stacked_vec_array[:, i] for i in range(stacked_vec_array.shape[1])]

        # Compute SVD of stacked data vectors
        summed_correlation_mats = inner_product(vecs, vecs) + inner_product(
            adv_vecs, adv_vecs)
        summed_correlation_mats_eigvals, summed_correlation_mats_eigvecs =\
            util.eigh(summed_correlation_mats)
        cross_correlation_mat = inner_product(vecs, adv_vecs)
        stacked_U = vec_array.dot(
            np.array(summed_correlation_mats_eigvecs)).dot(
            np.diag(summed_correlation_mats_eigvals ** -0.5))
        stacked_U_list = [stacked_U[:, i] for i in range(stacked_U.shape[1])]

        # Truncate stacked SVD if necessary
        if max_num_eigvals is not None and (
            max_num_eigvals < summed_correlation_mats_eigvals.size):
            summed_correlation_mats_eigvals = summed_correlation_mats_eigvals[
                :max_num_eigvals]
            summed_correlation_mats_eigvecs = summed_correlation_mats_eigvecs[
                :, :max_num_eigvals]
            stacked_U = stacked_U[:, :max_num_eigvals]
            stacked_U_list = stacked_U_list[:max_num_eigvals]

        # Project data matrices
        vec_array_proj = np.array(
            vec_array *
            summed_correlation_mats_eigvecs *
            summed_correlation_mats_eigvecs.H)
        adv_vec_array_proj = np.array(
            adv_vec_array *
            summed_correlation_mats_eigvecs *
            summed_correlation_mats_eigvecs.H)
        vecs_proj = [
            vec_array_proj[:, i] for i in range(vec_array_proj.shape[1])]
        adv_vecs_proj = [
            adv_vec_array_proj[:, i]
            for i in range(adv_vec_array_proj.shape[1])]

        # SVD of projected snapshots
        proj_correlation_mat = inner_product(vecs_proj, vecs_proj)
        proj_correlation_mat_eigvals, proj_correlation_mat_eigvecs =\
            util.eigh(proj_correlation_mat)
        proj_U = vec_array.dot(
            np.array(proj_correlation_mat_eigvecs)).dot(
            np.diag(proj_correlation_mat_eigvals ** -0.5))
        proj_U_list = [proj_U[:, i] for i in range(proj_U.shape[1])]

        # Truncate stacked SVD if necessary
        if max_num_eigvals is not None and (
            max_num_eigvals < proj_correlation_mat_eigvals.size):
            proj_correlation_mats_eigvals = proj_correlation_mats_eigvals[
                :max_num_eigvals]
            proj_correlation_mats_eigvecs = proj_correlation_mats_eigvecs[
                :, :max_num_eigvals]
            proj_U = proj_U[:, :max_num_eigvals]
            proj_U_list = proj_U_list[:max_num_eigvals]

        # Compute eigendecomposition of low order linear operator
        A_tilde = inner_product(proj_U_list, adv_vecs_proj).dot(
            np.array(proj_correlation_mat_eigvecs)).dot(
            np.diag(proj_correlation_mat_eigvals ** -0.5))
        eigvals, R_low_order_eigvecs, L_low_order_eigvecs =\
            util.eig_biorthog(A_tilde, scale_choice='left')
        R_low_order_eigvecs = np.mat(R_low_order_eigvecs)
        L_low_order_eigvecs = np.mat(L_low_order_eigvecs)

        # Compute build coefficients
        build_coeffs_proj = (
            summed_correlation_mats_eigvecs.dot(
            summed_correlation_mats_eigvecs.T.dot(
            proj_correlation_mat_eigvecs.dot(
            np.diag(proj_correlation_mat_eigvals ** -0.5)).dot(
            R_low_order_eigvecs))))
        build_coeffs_exact = (
            summed_correlation_mats_eigvecs.dot(
            summed_correlation_mats_eigvecs.T.dot(
            proj_correlation_mat_eigvecs.dot(
            np.diag(proj_correlation_mat_eigvals ** -0.5)).dot(
            R_low_order_eigvecs).dot(
            np.diag(eigvals ** -1.)))))

        # Compute modes
        modes_proj = vec_array_proj.dot(build_coeffs_proj)
        modes_exact = adv_vec_array_proj.dot(build_coeffs_exact)
        adj_modes = proj_U.dot(L_low_order_eigvecs)
        adj_modes_list = [
            np.array(adj_modes[:, i]) for i in range(adj_modes.shape[1])]

        return (
            modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
            L_low_order_eigvecs, summed_correlation_mats_eigvals,
            summed_correlation_mats_eigvecs, proj_correlation_mat_eigvals,
            proj_correlation_mat_eigvecs, cross_correlation_mat, adj_modes)


    def _helper_test_1D_array_to_sign(
        self, true_vals, test_vals, rtol=1e-12, atol=1e-16):
        # Check that shapes are the same
        self.assertEqual(len(true_vals.shape), 1)
        self.assertEqual(len(test_vals.shape), 1)
        self.assertEqual(true_vals.size, test_vals.size)

        # Check values entry by entry.
        for idx in range(true_vals.size):
            true_val = true_vals[idx]
            test_val = test_vals[idx]
            self.assertTrue(
                np.allclose(true_val, test_val, rtol=rtol, atol=atol)
                or
                np.allclose(-true_val, test_val, rtol=rtol, atol=atol))


    def _helper_test_mat_to_sign(
        self, true_vals, test_vals, rtol=1e-12, atol=1e-16):
        # Check that shapes are the same
        self.assertEqual(len(true_vals.shape), len(test_vals.shape))
        for shape_idx in range(len(true_vals.shape)):
            self.assertEqual(
                true_vals.shape[shape_idx], test_vals.shape[shape_idx])

        # Check values column by columns.  To allow for matrices or arrays,
        # turn columns into arrays and squeeze them (forcing 1D arrays).  This
        # avoids failures due to trivial shape mismatches.
        for col_idx in range(true_vals.shape[1]):
            true_col = np.array(true_vals[:, col_idx]).squeeze()
            test_col = np.array(test_vals[:, col_idx]).squeeze()
            self.assertTrue(
                np.allclose(true_col, test_col, rtol=rtol, atol=atol)
                or
                np.allclose(-true_col, test_col, rtol=rtol, atol=atol))


    def _helper_check_decomp(
        self, vec_array,  vec_handles, adv_vec_array=None,
        adv_vec_handles=None, max_num_eigvals=None):
        # Set tolerance.
        rtol = 1e-10
        atol = 1e-12

        # Compute reference DMD values
        (eigvals_true, R_low_order_eigvecs_true, L_low_order_eigvecs_true,
            summed_correlation_mats_eigvals_true,
            summed_correlation_mats_eigvecs_true,
            proj_correlation_mat_eigvals_true,
            proj_correlation_mat_eigvecs_true) = (
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            adv_vec_array=adv_vec_array,
            max_num_eigvals=max_num_eigvals))[2:-2]

        # Compute DMD using modred
        (eigvals_returned,  R_low_order_eigvecs_returned,
            L_low_order_eigvecs_returned,
            summed_correlation_mats_eigvals_returned,
            summed_correlation_mats_eigvecs_returned,
            proj_correlation_mat_eigvals_returned,
            proj_correlation_mat_eigvecs_returned
            ) = self.my_DMD.compute_decomp(
            vec_handles, adv_vec_handles=adv_vec_handles,
            max_num_eigvals=max_num_eigvals)

        # Test that matrices were correctly computed.  For build coeffs, check
        # column by column, as it is ok to be off by a negative sign.
        np.testing.assert_allclose(
            self.my_DMD.eigvals, eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            self.my_DMD.R_low_order_eigvecs, R_low_order_eigvecs_true,
            rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            self.my_DMD.L_low_order_eigvecs, L_low_order_eigvecs_true,
            rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            self.my_DMD.summed_correlation_mats_eigvals,
            summed_correlation_mats_eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            self.my_DMD.summed_correlation_mats_eigvecs,
            summed_correlation_mats_eigvecs_true, rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            self.my_DMD.proj_correlation_mat_eigvals,
            proj_correlation_mat_eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            self.my_DMD.proj_correlation_mat_eigvecs,
            proj_correlation_mat_eigvecs_true, rtol=rtol, atol=atol)

        # Test that matrices were correctly returned
        np.testing.assert_allclose(
            eigvals_returned, eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            R_low_order_eigvecs_returned, R_low_order_eigvecs_true, rtol=rtol,
            atol=atol)
        self._helper_test_mat_to_sign(
            L_low_order_eigvecs_returned, L_low_order_eigvecs_true, rtol=rtol,
            atol=atol)
        np.testing.assert_allclose(
            summed_correlation_mats_eigvals_returned,
            summed_correlation_mats_eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            summed_correlation_mats_eigvecs_returned,
            summed_correlation_mats_eigvecs_true, rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            proj_correlation_mat_eigvals_returned,
            proj_correlation_mat_eigvals_true, rtol=rtol, atol=atol)
        self._helper_test_mat_to_sign(
            proj_correlation_mat_eigvecs_returned,
            proj_correlation_mat_eigvecs_true, rtol=rtol, atol=atol)


    def _helper_check_modes(self, modes_true, mode_path_list):
        # Set tolerance.
        rtol = 1e-10
        atol = 1e-12

        # Load all modes into matrix, compare to modes from direct computation
        modes_computed = np.zeros(modes_true.shape, dtype=complex)
        for i, path in enumerate(mode_path_list):
            modes_computed[:, i] = V.VecHandlePickle(path).get()
        np.testing.assert_allclose(
            modes_true, modes_computed, rtol=rtol, atol=atol)


    #@unittest.skip('Testing something else.')
    def test_compute_decomp(self):
        """Test DMD decomposition"""
        # Define an array of vectors, with corresponding handles
        vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.vec_handles):
                handle.put(np.array(vec_array[:, vec_index]).squeeze())

        # Check modred against direct computation, for a sequential dataset
        # (always need to truncate for TLSDMD).
        parallel.barrier()
        self._helper_check_decomp(vec_array, self.vec_handles,
            max_num_eigvals=self.max_num_eigvals)

        # Create more data, to check a non-sequential dataset
        adv_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.adv_vec_handles):
                handle.put(np.array(adv_vec_array[:, vec_index]).squeeze())

        # Check modred against direct computation, for a non-sequential dataset
        # (always need to truncate for TLSDMD).
        parallel.barrier()
        self._helper_check_decomp(
            vec_array, self.vec_handles, adv_vec_array=adv_vec_array,
            adv_vec_handles=self.adv_vec_handles,
            max_num_eigvals=self.max_num_eigvals)

        # Check that if mismatched sets of handles are passed in, an error is
        # raised.
        self.assertRaises(ValueError, self.my_DMD.compute_decomp,
            self.vec_handles, self.adv_vec_handles[:-1])


    #@unittest.skip('Testing something else.')
    def test_compute_modes(self):
        """Test building of modes."""
        # Generate path names for saving modes to disk
        mode_path = join(self.test_dir, 'dmd_mode_%03d.pkl')

        ### SEQUENTIAL DATASET ###
        # Generate data
        seq_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.vec_handles):
                handle.put(np.array(seq_vec_array[:, vec_index]).squeeze())

        # Compute DMD directly from data (must truncate for TLSDMD)
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, summed_correlation_mats_eigvals,
        summed_correlation_mats_eigvecs, proj_correlation_mat_eigvals,
        proj_correlation_mat_eigvecs) = self._helper_compute_DMD_from_data(
            seq_vec_array, util.InnerProductBlock(np.vdot),
            max_num_eigvals=self.max_num_eigvals)[:-2]

        # Set the build_coeffs attribute of an empty DMD object each time, so
        # that the modred computation uses the same coefficients as the direct
        # computation.
        parallel.barrier()
        self.my_DMD.eigvals = eigvals
        self.my_DMD.R_low_order_eigvecs = R_low_order_eigvecs
        self.my_DMD.summed_correlation_mats_eigvals =\
            summed_correlation_mats_eigvals
        self.my_DMD.summed_correlation_mats_eigvecs =\
            summed_correlation_mats_eigvecs
        self.my_DMD.proj_correlation_mat_eigvals = proj_correlation_mat_eigvals
        self.my_DMD.proj_correlation_mat_eigvecs = proj_correlation_mat_eigvecs

        # Generate mode paths for saving modes to disk
        seq_mode_path_list = [
            mode_path % i for i in range(eigvals.size)]
        seq_mode_indices = range(len(seq_mode_path_list))

        # Compute modes by passing in handles
        self.my_DMD.compute_exact_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list],
            adv_vec_handles=self.vec_handles[1:])
        self._helper_check_modes(modes_exact, seq_mode_path_list)
        self.my_DMD.compute_proj_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list],
            vec_handles=self.vec_handles)
        self._helper_check_modes(modes_proj, seq_mode_path_list)

        # Compute modes without passing in handles, so first set full
        # sequential dataset as vec_handles.
        self.my_DMD.vec_handles = self.vec_handles
        self.my_DMD.compute_exact_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list])
        self._helper_check_modes(modes_exact, seq_mode_path_list)
        self.my_DMD.compute_proj_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list])
        self._helper_check_modes(modes_proj, seq_mode_path_list)

        # For exact modes, also compute by setting adv_vec_handles
        self.my_DMD.vec_handles = None
        self.my_DMD.adv_vec_handles = self.vec_handles[1:]
        self.my_DMD.compute_exact_modes(seq_mode_indices,
            [V.VecHandlePickle(path) for path in seq_mode_path_list])
        self._helper_check_modes(modes_exact, seq_mode_path_list)

        ### NONSEQUENTIAL DATA ###
        # Generate data
        vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        adv_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, (handle, adv_handle) in enumerate(
                zip(self.vec_handles, self.adv_vec_handles)):
                handle.put(np.array(vec_array[:, vec_index]).squeeze())
                adv_handle.put(np.array(adv_vec_array[:, vec_index]).squeeze())

        # Compute DMD directly from data (must truncate for TLSDMD)
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, summed_correlation_mats_eigvals,
        summed_correlation_mats_eigvecs, proj_correlation_mat_eigvals,
        proj_correlation_mat_eigvecs ) = self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            adv_vec_array=adv_vec_array,
            max_num_eigvals=self.max_num_eigvals)[:-2]

        # Set the build_coeffs attribute of an empty DMD object each time, so
        # that the modred computation uses the same coefficients as the direct
        # computation.
        parallel.barrier()
        self.my_DMD.eigvals = eigvals
        self.my_DMD.R_low_order_eigvecs = R_low_order_eigvecs
        self.my_DMD.summed_correlation_mats_eigvals =\
            summed_correlation_mats_eigvals
        self.my_DMD.summed_correlation_mats_eigvecs =\
            summed_correlation_mats_eigvecs
        self.my_DMD.proj_correlation_mat_eigvals = proj_correlation_mat_eigvals
        self.my_DMD.proj_correlation_mat_eigvecs = proj_correlation_mat_eigvecs

        # Generate mode paths for saving modes to disk
        mode_path_list = [
            mode_path % i for i in range(eigvals.size)]
        mode_indices = range(len(mode_path_list))

        # Compute modes by passing in handles
        self.my_DMD.compute_exact_modes(mode_indices,
            [V.VecHandlePickle(path) for path in mode_path_list],
            adv_vec_handles=self.adv_vec_handles)
        self._helper_check_modes(modes_exact, mode_path_list)
        self.my_DMD.compute_proj_modes(mode_indices,
            [V.VecHandlePickle(path) for path in mode_path_list],
            vec_handles=self.vec_handles)
        self._helper_check_modes(modes_proj, mode_path_list)

        # Compute modes without passing in handles, so first set full
        # sequential dataset as vec_handles.
        self.my_DMD.vec_handles = self.vec_handles
        self.my_DMD.adv_vec_handles = self.adv_vec_handles
        self.my_DMD.compute_exact_modes(mode_indices,
            [V.VecHandlePickle(path) for path in mode_path_list])
        self._helper_check_modes(modes_exact, mode_path_list)
        self.my_DMD.compute_proj_modes(mode_indices,
            [V.VecHandlePickle(path) for path in mode_path_list])
        self._helper_check_modes(modes_proj, mode_path_list)


    #@unittest.skip('Testing something else.')
    def test_compute_spectrum(self):
        """Test DMD spectrum"""
        rtol = 1e-10
        atol = 1e-12

        # Define an array of vectors, with corresponding handles
        vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.vec_handles):
                handle.put(np.array(vec_array[:, vec_index]).squeeze())

        # Compute DMD manually and then set the data in a DMDHandles object.
        # This way, we test only the task of computing the spectral
        # coefficients, and not also the task of computing the decomposition.
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, summed_correlation_mats_eigvals,
        summed_correlation_mats_eigvecs, proj_correlation_mat_eigvals,
        proj_correlation_mat_eigvecs, cross_correlation_mat, adj_modes) =\
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            max_num_eigvals=self.max_num_eigvals)
        self.my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        self.my_DMD.proj_correlation_mat_eigvals = proj_correlation_mat_eigvals
        self.my_DMD.proj_correlation_mat_eigvecs = proj_correlation_mat_eigvecs

        # Check that spectral coefficients computed using adjoints match those
        # computed using a direct projection onto the adjoint modes
        parallel.barrier()
        spectral_coeffs = self.my_DMD.compute_spectrum()
        vec_array_proj = np.array(
            vec_array[:, :-1] *
            summed_correlation_mats_eigvecs *
            summed_correlation_mats_eigvecs.H)
        spectral_coeffs_true = np.abs(np.array(
            np.dot(adj_modes.conj().T, vec_array_proj[:, 0]))).squeeze()
        np.testing.assert_allclose(
            spectral_coeffs, spectral_coeffs_true, rtol=rtol, atol=atol)

        # Create more data, to check a non-sequential dataset
        adv_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.adv_vec_handles):
                handle.put(np.array(adv_vec_array[:, vec_index]).squeeze())

        # Compute DMD manually and then set the data in a DMDHandles object.
        # This way, we test only the task of computing the spectral
        # coefficients, and not also the task of computing the decomposition.
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, summed_correlation_mats_eigvals,
        summed_correlation_mats_eigvecs, proj_correlation_mat_eigvals,
        proj_correlation_mat_eigvecs, cross_correlation_mat, adj_modes) =\
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            adv_vec_array=adv_vec_array,
            max_num_eigvals=self.max_num_eigvals)
        self.my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        self.my_DMD.proj_correlation_mat_eigvals = proj_correlation_mat_eigvals
        self.my_DMD.proj_correlation_mat_eigvecs = proj_correlation_mat_eigvecs

        # Check spectral coefficients using a direct projection onto the
        # adjoint modes.  (Must always truncate for TLSDMD.)
        parallel.barrier()
        spectral_coeffs = self.my_DMD.compute_spectrum()
        vec_array_proj = np.array(
            vec_array *
            summed_correlation_mats_eigvecs *
            summed_correlation_mats_eigvecs.H)
        spectral_coeffs_true = np.abs(np.array(
            np.dot(adj_modes.conj().T, vec_array_proj[:, 0]))).squeeze()
        np.testing.assert_allclose(
            spectral_coeffs, spectral_coeffs_true, rtol=rtol, atol=atol)


    #@unittest.skip('Testing something else.')
    def test_compute_proj_coeffs(self):
        """Test projection coefficients"""
        rtol = 1e-10
        atol = 1e-12

        # Define an array of vectors, with corresponding handles
        vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.vec_handles):
                handle.put(np.array(vec_array[:, vec_index]).squeeze())

        # Compute DMD manually and then set the data in a TLSqrDMDHandles
        # object.  This way, we test only the task of computing the projection
        # coefficients, and not also the task of computing the decomposition.
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, summed_correlation_mats_eigvals,
        summed_correlation_mats_eigvecs, proj_correlation_mat_eigvals,
        proj_correlation_mat_eigvecs, cross_correlation_mat, adj_modes) =\
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            max_num_eigvals=self.max_num_eigvals)
        self.my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        self.my_DMD.proj_correlation_mat_eigvals = proj_correlation_mat_eigvals
        self.my_DMD.proj_correlation_mat_eigvecs = proj_correlation_mat_eigvecs
        self.my_DMD.summed_correlation_mats_eigvecs =\
            summed_correlation_mats_eigvecs
        self.my_DMD.cross_correlation_mat = cross_correlation_mat

        # Check the spectral coefficient values.  Compare the formula
        # implemented in modred to a direct projection onto the adjoint modes.
        parallel.barrier()
        proj_coeffs, adv_proj_coeffs = self.my_DMD.compute_proj_coeffs()
        vec_array_proj = np.array(
            vec_array[:, :-1] *
            summed_correlation_mats_eigvecs * summed_correlation_mats_eigvecs.H)
        adv_vec_array_proj = np.array(
            vec_array[:, 1:] *
            summed_correlation_mats_eigvecs * summed_correlation_mats_eigvecs.H)
        proj_coeffs_true = np.dot(
            adj_modes.conj().T, vec_array_proj)
        adv_proj_coeffs_true = np.dot(
            adj_modes.conj().T, adv_vec_array_proj)
        np.testing.assert_allclose(
            proj_coeffs, proj_coeffs_true, rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            adv_proj_coeffs, adv_proj_coeffs_true, rtol=rtol, atol=atol)

        # Create more data, to check a non-sequential dataset
        adv_vec_array = parallel.call_and_bcast(np.random.random,
            ((self.num_states, self.num_vecs)))
        if parallel.is_rank_zero():
            for vec_index, handle in enumerate(self.adv_vec_handles):
                handle.put(np.array(adv_vec_array[:, vec_index]).squeeze())

        # Compute DMD manually and then set the data in a TLSqrDMDHandles
        # object.  This way, we test only the task of computing the projection
        # coefficients, and not also the task of computing the decomposition.
        (modes_exact, modes_proj, eigvals, R_low_order_eigvecs,
        L_low_order_eigvecs, summed_correlation_mats_eigvals,
        summed_correlation_mats_eigvecs, proj_correlation_mat_eigvals,
        proj_correlation_mat_eigvecs, cross_correlation_mat, adj_modes) =\
            self._helper_compute_DMD_from_data(
            vec_array, util.InnerProductBlock(np.vdot),
            adv_vec_array=adv_vec_array, max_num_eigvals=self.max_num_eigvals)
        self.my_DMD.L_low_order_eigvecs = L_low_order_eigvecs
        self.my_DMD.proj_correlation_mat_eigvals = proj_correlation_mat_eigvals
        self.my_DMD.proj_correlation_mat_eigvecs = proj_correlation_mat_eigvecs
        self.my_DMD.summed_correlation_mats_eigvecs =\
            summed_correlation_mats_eigvecs
        self.my_DMD.cross_correlation_mat = cross_correlation_mat

        # Check the spectral coefficient values.  Compare the formula
        # implemented in modred to a direct projection onto the adjoint modes.
        parallel.barrier()
        proj_coeffs, adv_proj_coeffs= self.my_DMD.compute_proj_coeffs()
        vec_array_proj = np.array(
            vec_array *
            summed_correlation_mats_eigvecs * summed_correlation_mats_eigvecs.H)
        adv_vec_array_proj = np.array(
            adv_vec_array *
            summed_correlation_mats_eigvecs * summed_correlation_mats_eigvecs.H)
        proj_coeffs_true = np.dot(adj_modes.conj().T, vec_array_proj)
        adv_proj_coeffs_true = np.dot(adj_modes.conj().T, adv_vec_array_proj)
        np.testing.assert_allclose(
            proj_coeffs, proj_coeffs_true, rtol=rtol, atol=atol)
        np.testing.assert_allclose(
            adv_proj_coeffs, adv_proj_coeffs_true,rtol=rtol, atol=atol)


if __name__ == '__main__':
    unittest.main()
