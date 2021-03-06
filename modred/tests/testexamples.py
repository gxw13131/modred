#!/usr/bin/env python
""" !!This file is not used!!

Examples are used with ../examples/Makefile."""
from __future__ import absolute_import
from past.builtins import execfile
from future.builtins import range
import unittest
import os, sys
from os.path import join
from shutil import rmtree

import modred.parallel as parallel


# Directory we start from, absolute path.
running_dir = os.getcwd()
# Directory of this test file, abs path.
this_file_dir = os.path.dirname(os.path.abspath(__file__))
# Directory containing example files, abs path.
examples_dir = join(join(this_file_dir, '..'), 'examples')

"""
# Redefine stdout and stderr to suppress output from the examples in the tests.
class np.PrintingStream(object):
    def write(self,data): pass
    #def read(self,data): pass
    def flush(self): pass
    def close(self): pass

old_printers = [sys.stdout,sys.stderr,sys.stdin,sys.__stdout__,
    sys.__stderr__,sys.__stdin__][:]

def printing(on):
    #Takes True or False
    if not on:
        sys.stdout = np.PrintingStream()
        sys.stderr = np.PrintingStream()
        #sys.stdin = np.PrintingStream()
        sys.__stdout__ = np.PrintingStream()
        sys.__stderr__ = np.PrintingStream()
        #sys.__stdin__ = np.PrintingStream()

    else:
        (sys.stdout,sys.stderr,sys.stdin,sys.__stdout__,sys.__stderr__, \
        sys.__stdin__) = old_printers
"""


class TestExamples(unittest.TestCase):
    def setUp(self):
        parallel.barrier()
        self.test_dir = join(running_dir, 'DELETE_ME_test_tutorial_examples')
        if not os.access('.', os.W_OK):
            raise RuntimeError('Cannot write to current directory')
        if not os.path.isdir(self.test_dir) and parallel.is_rank_zero():
            os.mkdir(self.test_dir)
        parallel.barrier()

        os.chdir(self.test_dir)


    def tearDown(self):
        os.chdir(running_dir)
        parallel.barrier()
        if parallel.is_rank_zero():
            rmtree(self.test_dir, ignore_errors=True)
        parallel.barrier()


    @unittest.skip('Test with Makefile in examples directory instead')
    def test_tutorial_examples(self):
        """Runs all tutorial examples. If run without errors, passes test"""
        example_script = 'tutorial_ex%d.py'
        for example_num in range(1, 7):
            # Example 3 isn't meant to work in parallel
            if not (parallel.is_distributed() and example_num != 3):
                #printing(False)
                parallel.barrier()
                execfile(join(examples_dir, example_script%example_num))
                parallel.barrier()
                #printing(True)


    @unittest.skip('Unnecessary test for user')
    def test_benchmark(self):
        from . import benchmark as B
        num_states = 14
        num_bases = 10
        num_sums = 5
        max_vecs_per_node = 4
        time = B.lin_combine(num_states, num_bases, num_sums,
            max_vecs_per_node, verbosity=0)
        self.assertEqual(type(time), float)

        num_rows = 10
        num_cols = 12
        time = B.inner_product_mat(num_states, num_rows, num_cols,
            max_vecs_per_node, verbosity=0)
        self.assertEqual(type(time), float)

        time = B.symmetric_inner_product_mat(num_states, num_rows,
            max_vecs_per_node, verbosity=0)
        self.assertEqual(type(time), float)


if __name__ == '__main__':
    unittest.main()
