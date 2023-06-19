"""
Hooks for adding tags, filtering and setting job resources in ReFrame tests
"""
import math
import shlex

import reframe as rfm

from eessi.testsuite.constants import DEVICES, FEATURES, SCALES
from eessi.testsuite.utils import get_max_avail_gpus_per_node, is_cuda_required_module, log

PROCESSOR_INFO_MISSING = '''
This test requires the number of CPUs to be known for the partition it runs on.
Check that processor information is either autodetected
(see https://reframe-hpc.readthedocs.io/en/stable/configure.html#proc-autodetection),
or manually set in the ReFrame configuration file
(see https://reframe-hpc.readthedocs.io/en/stable/config_reference.html#processor-info).
'''


def assign_one_task_per_compute_unit(test: rfm.RegressionTest, compute_unit: str):
    """
    Assign one task per compute unit (DEVICES['CPU'], DEVICES['CPU_SOCKET'] or DEVICES['GPU']).
    Automatically sets num_tasks, num_tasks_per_node, num_cpus_per_task, and num_gpus_per_node,
    based on the current scale and the current partition’s num_cpus, max_avail_gpus_per_node and num_nodes.
    For GPU tests, one task per GPU is set, and num_cpus_per_task is based on the ratio of CPU-cores/GPUs.
    For CPU tests, one task per CPU is set, and num_cpus_per_task is set to 1.
    Total task count is determined based on the number of nodes to be used in the test.
    Behaviour of this function is (usually) sensible for MPI tests.
    """
    test.max_avail_cpus_per_node = test.current_partition.processor.num_cpus
    if test.max_avail_cpus_per_node is None:
        raise AttributeError(PROCESSOR_INFO_MISSING)

    # Check if either node_part, or default_num_cpus_per_node and default_num_gpus_per_node are set correctly
    if not (
        type(test.node_part) == int or
        (type(test.default_num_cpus_per_node) == int and type(test.default_num_gpus_per_node) == int)
    ):
        raise ValueError(
            f'Either node_part ({test.node_part}), or default_num_cpus_per_node ({test.default_num_cpus_per_node}) and'
            f' default num_gpus_per_node ({test.default_num_gpus_per_node}) must be defined and have integer values.'
        )

    # Check if the default number of cpus per node is already defined in the test
    # (e.g. by earlier hooks like set_tag_scale).
    # If so, check if it doesn't exceed the maximum available.
    # If not, set default_num_cpus_per_node based on the maximum available cpus and node_part
    if test.default_num_cpus_per_node:
        # may skip if not enough CPUs
        test.skip_if(
            test.default_num_cpus_per_node > test.max_avail_cpus_per_node,
            f'Requested CPUs per node ({test.default_num_cpus_per_node}) is higher than max available'
            f' ({test.max_avail_cpus_per_node}) in current partition ({test.current_partition.name}).'
        )
    else:
        # no default set yet, so setting one
        test.default_num_cpus_per_node = int(test.max_avail_cpus_per_node / test.node_part)

    log(f'default_num_cpus_per_node set to {test.default_num_cpus_per_node}')

    if compute_unit == DEVICES['GPU']:
        _assign_one_task_per_gpu(test)
    elif compute_unit == DEVICES['CPU']:
        _assign_one_task_per_cpu(test)
    elif compute_unit == DEVICES['CPU_SOCKET']:
        _assign_one_task_per_cpu_socket(test)
    else:
        raise ValueError(f'compute unit {compute_unit} is currently not supported')

def _assign_one_task_per_cpu_socket(test: rfm.RegressionTest):
    """
    Sets num_tasks_per_node and num_cpus_per_task such that it will run one task per cpu socket,
    unless specified with:
    --setvar num_tasks_per_node=<x> and/or
    --setvar num_cpus_per_task=<y>.

    Variables:
    - default_num_cpus_per_node: default number of CPUs per node as defined in the test
    (e.g. by earlier hooks like set_tag_scale)


    Default resources requested:
    - num_tasks_per_node = default_num_cpus_per_node
    - num_cpus_per_task = default_num_cpus_per_node / num_tasks_per_node
    """
    # neither num_tasks_per_node nor num_cpus_per_task are set
    if not test.num_tasks_per_node and not test.num_cpus_per_task:
        if test.current_partition.processor.num_sockets:
            test.num_tasks_per_node = test.current_partition.processor.num_sockets
            test.num_cpus_per_task = int(test.default_num_cpus_per_node / test.num_tasks_per_node)

    # num_tasks_per_node is not set, but num_cpus_per_task is
    elif not test.num_tasks_per_node:
        test.num_tasks_per_node = int(test.default_num_cpus_per_node / test.num_cpus_per_task)

    # num_cpus_per_task is not set, but num_tasks_per_node is
    elif not test.num_cpus_per_task:
        test.num_cpus_per_task = int(test.default_num_cpus_per_node / test.num_tasks_per_node)

    else:
        pass  # both num_tasks_per_node and num_cpus_per_node are already set

    test.num_tasks = test.num_nodes * test.num_tasks_per_node

def _assign_one_task_per_cpu(test: rfm.RegressionTest):
    """
    Sets num_tasks_per_node and num_cpus_per_task such that it will run one task per core,
    unless specified with:
    --setvar num_tasks_per_node=<x> and/or
    --setvar num_cpus_per_task=<y>.

    Variables:
    - default_num_cpus_per_node: default number of CPUs per node as defined in the test
    (e.g. by earlier hooks like set_tag_scale)


    Default resources requested:
    - num_tasks_per_node = default_num_cpus_per_node
    - num_cpus_per_task = default_num_cpus_per_node / num_tasks_per_node
    """
    # neither num_tasks_per_node nor num_cpus_per_node are set
    if not test.num_tasks_per_node and not test.num_cpus_per_task:
        test.num_tasks_per_node = test.default_num_cpus_per_node
        test.num_cpus_per_task = 1

    # num_tasks_per_node is not set, but num_cpus_per_node is
    elif not test.num_tasks_per_node:
        test.num_tasks_per_node = int(test.default_num_cpus_per_node / test.num_cpus_per_task)

    # num_cpus_per_node is not set, but num_tasks_per_node is
    elif not test.num_cpus_per_task:
        test.num_cpus_per_task = int(test.default_num_cpus_per_node / test.num_tasks_per_node)

    else:
        pass  # both num_tasks_per_node and num_cpus_per_node are already set

    test.num_tasks = test.num_nodes * test.num_tasks_per_node

    log(f'num_tasks_per_node set to {test.num_tasks_per_node}')
    log(f'num_cpus_per_task set to {test.num_cpus_per_task}')
    log(f'num_tasks set to {test.num_tasks}')


def _assign_one_task_per_gpu(test: rfm.RegressionTest):
    """
    Sets num_tasks_per_node, num_cpus_per_task, and num_gpus_per_node, unless specified with:
    --setvar num_tasks_per_node=<x> and/or
    --setvar num_cpus_per_task=<y> and/or
    --setvar num_gpus_per_node=<z>.

    Variables:
    - max_avail_gpus_per_node: maximum available number of GPUs per node
    - default_num_gpus_per_node: default number of GPUs per node as defined in the test
    (e.g. by earlier hooks like set_tag_scale)

    Default resources requested:
    - num_gpus_per_node = default_num_gpus_per_node
    - num_tasks_per_node = num_gpus_per_node
    - num_cpus_per_task = default_num_cpus_per_node / num_tasks_per_node

    If num_tasks_per_node is set, set num_gpus_per_node equal to either num_tasks_per_node or default_num_gpus_per_node
    (whichever is smallest), unless num_gpus_per_node is also set.
    """
    max_avail_gpus_per_node = get_max_avail_gpus_per_node(test)

    # Check if the default number of gpus per node is already defined in the test
    # (e.g. by earlier hooks like set_tag_scale).
    # If so, check if it doesn't exceed the maximum available.
    # If not, set default_num_gpus_per_node based on the maximum available gpus and node_part
    if test.default_num_gpus_per_node:
        # may skip if not enough GPUs
        test.skip_if(
            test.default_num_gpus_per_node > max_avail_gpus_per_node,
            f'Requested GPUs per node ({test.default_num_gpus_per_node}) is higher than max available'
            f' ({max_avail_gpus_per_node}) in current partition ({test.current_partition.name}).'
        )
    else:
        # no default set yet, so setting one
        test.default_num_gpus_per_node = math.ceil(max_avail_gpus_per_node / test.node_part)

    # neither num_tasks_per_node nor num_gpus_per_node are set
    if not test.num_tasks_per_node and not test.num_gpus_per_node:
        test.num_gpus_per_node = test.default_num_gpus_per_node
        test.num_tasks_per_node = test.num_gpus_per_node

    # num_tasks_per_node is not set, but num_gpus_per_node is
    elif not test.num_tasks_per_node:
        test.num_tasks_per_node = test.num_gpus_per_node

    # num_gpus_per_node is not set, but num_tasks_per_node is
    elif not test.num_gpus_per_node:
        test.num_gpus_per_node = min(test.num_tasks_per_node, test.default_num_gpus_per_node)

    else:
        pass  # both num_tasks_per_node and num_gpus_per_node are already set

    # num_cpus_per_task is not set
    if not test.num_cpus_per_task:
        # limit num_cpus_per_task to the maximum available cpus per gpu
        test.num_cpus_per_task = min(
            int(test.default_num_cpus_per_node / test.num_tasks_per_node),
            int(test.max_avail_cpus_per_node / max_avail_gpus_per_node)
        )

    test.num_tasks = test.num_nodes * test.num_tasks_per_node

    log(f'num_gpus_per_node set to {test.num_gpus_per_node}')
    log(f'num_tasks_per_node set to {test.num_tasks_per_node}')
    log(f'num_cpus_per_task set to {test.num_cpus_per_task}')
    log(f'num_tasks set to {test.num_tasks}')


def filter_valid_systems_by_device_type(test: rfm.RegressionTest, required_device_type: str):
    """
    Filter valid_systems by required device type and by whether the module supports CUDA,
    unless valid_systems is specified with --setvar valid_systems=<comma-separated-list>.
    """
    if not test.valid_systems:
        is_cuda_module = is_cuda_required_module(test.module_name)
        valid_systems = ''

        if is_cuda_module and required_device_type == DEVICES['GPU']:
            # CUDA modules and when using a GPU require partitions with 'gpu' feature
            valid_systems = f'+{FEATURES["GPU"]}'

        elif required_device_type == DEVICES['CPU']:
            # Using the CPU requires partitions with 'cpu' feature
            # Note: making 'cpu' an explicit feature allows e.g. skipping CPU-based tests on GPU partitions
            valid_systems = f'+{FEATURES["CPU"]}'

        elif not is_cuda_module and required_device_type == DEVICES['GPU']:
            # Invalid combination: a module without GPU support cannot use a GPU
            valid_systems = ''

        if valid_systems:
            test.valid_systems = [valid_systems]

    log(f'valid_systems set to {test.valid_systems}')


def set_modules(test: rfm.RegressionTest):
    """
    Skip current test if module_name is not among a list of modules,
    specified with --setvar modules=<comma-separated-list>.
    """
    if test.modules and test.module_name not in test.modules:
        test.valid_systems = []
        log(f'valid_systems set to {test.valid_systems}')

    test.modules = [test.module_name]
    log(f'modules set to {test.modules}')


def set_tag_scale(test: rfm.RegressionTest):
    """Set resources and tag based on current scale"""
    scale = test.scale
    test.num_nodes = SCALES[scale]['num_nodes']
    test.default_num_cpus_per_node = SCALES[scale].get('num_cpus_per_node')
    test.default_num_gpus_per_node = SCALES[scale].get('num_gpus_per_node')
    test.node_part = SCALES[scale].get('node_part')
    test.tags.add(scale)
    log(f'tags set to {test.tags}')


def check_custom_executable_opts(test: rfm.RegressionTest, num_default: int = 0):
    """"
    Check if custom executable options were added with --setvar executable_opts=<x>.
    """
    # normalize options
    test.executable_opts = shlex.split(' '.join(test.executable_opts))
    test.has_custom_executable_opts = False
    if len(test.executable_opts) > num_default:
        test.has_custom_executable_opts = True
    log(f'has_custom_executable_opts set to {test.has_custom_executable_opts}')


def set_compact_process_binding(test: rfm.RegressionTest):
    """
    This hook sets a binding policy for process binding.
    More specifically, it will bind each process to subsequent domains of test.num_cpus_per_task cores.

    A few examples:
    - Pure MPI (test.num_cpus_per_task = 1) will result in binding 1 process to each core.
      this will happen in a compact way, i.e. rank 0 to core 0, rank 1 to core 1, etc
    - Hybrid MPI-OpenMP, e.g. test.num_cpus_per_task = 4 will result in binding 1 process to subsequent sets of 4 cores.
      I.e. rank 0 to core 0-3, rank 1 to core 4-7, rank 2 to core 8-11, etc

    It is hard to do this in a portable way. Currently supported for process binding are:
    - Intel MPI (through I_MPI_PIN_DOMAIN)
    - OpenMPI (through OMPI_MCA_rmaps_base_mapping_policy)
    - srun (LIMITED SUPPORT: through SLURM_CPU_BIND, but only effective if task/affinity plugin is enabled)
    """

    # Do binding for intel and OpenMPI's mpirun, and srun
    # Other launchers may or may not do the correct binding
    test.env_vars['I_MPI_PIN_DOMAIN'] = '%s:compact' % test.num_cpus_per_task
    test.env_vars['OMPI_MCA_rmaps_base_mapping_policy'] = 'node:PE=%s' % test.num_cpus_per_task
    # Default binding for SLURM. Only effective if the task/affinity plugin is enabled
    # and when number of tasks times cpus per task equals either socket, core or thread count
    test.env_vars['SLURM_CPU_BIND'] = 'q'


def set_compact_thread_binding(test: rfm.RegressionTest):
    """
    This hook sets a binding policy for thread binding.
    It sets a number of environment variables to try and set a sensible binding for OPENMP tasks.

    Thread binding is supported for:
    - GNU OpenMP (through OMP_NUM_THREADS, OMP_PLACES and OMP_PROC_BIND)
    - Intel OpenMP (through KMP_AFFINITY)
    """

    # Set thread binding
    test.env_vars['OMP_NUM_THREADS'] = test.num_cpus_per_task
    test.env_vars['OMP_PLACES'] = 'cores'
    test.env_vars['OMP_PROC_BIND'] = 'close'
    # See https://www.intel.com/content/www/us/en/docs/cpp-compiler/developer-guide-reference/2021-8/thread-affinity-interface.html
    test.env_vars['KMP_AFFINITY'] = 'granularity=fine,compact,1,0'