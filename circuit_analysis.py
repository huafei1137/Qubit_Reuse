import qiskit
import sys
from qiskit import *
from qiskit.visualization.pulse_v2 import draw
from qiskit.visualization import dag_drawer
from qiskit.converters import circuit_to_dag,dag_to_circuit
from qiskit.transpiler import CouplingMap
from qiskit.visualization import plot_histogram
from qiskit.circuit import Reset
from qiskit.circuit.quantumregister import Qubit
from qiskit.circuit.library import Measure

def has_operation_on_qubit(circuit, qubit_index):
    """
    Checks if there is an operation on a specific qubit in the quantum circuit.

    :param QuantumCircuit circuit: The quantum circuit to check.
    :param int qubit_index: The index of the qubit to check for operations.
    :return: True if there is an operation on the qubit, False otherwise.
    """
    for _, qargs, _ in circuit.data:
        if any(qubit.index == qubit_index for qubit in qargs):
            return True
    return False    
            
from qiskit.converters import circuit_to_dag
from qiskit import QuantumCircuit
from qiskit.visualization import dag_drawer

def build_custom_dag(qiskit_dag):
    # Mapping from qiskit dag nodes to indices for our custom dag
    node_map = {node: idx for idx, node in enumerate(qiskit_dag.topological_op_nodes())}
    
    # Initialize adjacency list for the custom DAG
    adj_list = {node_map[node]: [] for node in qiskit_dag.topological_op_nodes()}

    # Add edges based on the order of operations on each qubit
    for qubit in qiskit_dag.qubits:
        prev_node = None
        for node in qiskit_dag.nodes_on_wire(qubit, only_ops=True):
            if prev_node is not None:
                # Add an edge from prev_node to node in the custom DAG
                adj_list[node_map[prev_node]].append(node_map[node])
            prev_node = node

    print(adj_list)
    return adj_list


def has_cycle(graph, start, i, j):
    visited = set()
    rec_stack = set()

    # Temporarily add the edge from i to j
    if i in graph:
        graph[i].append(j)
    else:
        graph[i] = [j]

    print(i, j, graph)
    def visit(node):
        if node in rec_stack:
            return True
        if node in visited:
            return False

        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if visit(neighbor):
                return True
        rec_stack.remove(node)
        return False

    cycle_detected = visit(start)

    # Remove the temporarily added edge
    if j in graph[i]:
        graph[i].remove(j)
    if not graph[i]:
        del graph[i]

    return cycle_detected


def share_same_gate(qiskit_dag, i, j):
    for node in qiskit_dag.topological_op_nodes():
        qubits = [qubit.index for qubit in node.qargs]
        if i in qubits and j in qubits:
            return True
    return False

def find_qubit_reuse_pairs(circuit):
    qiskit_dag = circuit_to_dag(circuit)
    # print(qiskit_dag)
    custom_dag = build_custom_dag(qiskit_dag)



    print(custom_dag)

    num_qubits = len(circuit.qubits)

    reusable_pairs = []

    for i in range(num_qubits):
        last_op_index_i = -1
        for index, (inst, qargs, cargs) in enumerate(circuit.data):
            if any(circuit.find_bit(q).index == i for q in qargs):
                last_op_index_i = index
        for j in range(num_qubits):
            first_op_index_j = -1
            for index, (inst, qargs, cargs) in enumerate(circuit.data):
                if any(circuit.find_bit(q).index == j for q in qargs):
                    first_op_index_j = index
                    break


            if i != j and not share_same_gate(qiskit_dag, i, j) and not has_cycle(custom_dag, last_op_index_i,last_op_index_i,first_op_index_j) and has_operation_on_qubit(circuit,i) and has_operation_on_qubit(circuit,j):
                reusable_pairs.append((i, j))

    return reusable_pairs








def remove_consecutive_duplicate_gates(circuit):
    """
    Removes consecutive duplicate gates, including measurement gates, from a quantum circuit.

    :param QuantumCircuit circuit: The quantum circuit to modify.
    :return: A new QuantumCircuit with consecutive duplicate gates removed.
    """
    new_circuit = QuantumCircuit(*circuit.qregs, *circuit.cregs)
    prev_inst, prev_qargs, prev_cargs = None, None, None

    for inst, qargs, cargs in circuit.data:
        # Check if the current gate is a duplicate of the previous gate
        if inst == prev_inst and qargs == prev_qargs and cargs == prev_cargs:
            continue

        new_circuit.append(inst, qargs, cargs)
        prev_inst, prev_qargs, prev_cargs = inst, qargs, cargs

    return new_circuit
def modify_circuit(circuit, pair):
    """
    Modifies the given circuit by replacing operations on qubit j with qubit i,
    and reordering them to occur after the last use, measurement, and reset of qubit i.

    :param QuantumCircuit circuit: The quantum circuit to modify
    :param tuple pair: A tuple (i, j) indicating the qubits to be swapped
    """
    i, j = pair

    # Ensure the circuit has a classical register for measurement
    if not circuit.cregs:
        circuit.add_register(ClassicalRegister(1))

    # Store all operations and find the last operation involving qubit i
    operations = []
    check_list = []
    get_list = []
    visited = []
    last_op_index_i = -1
    for index, (inst, qargs, cargs) in enumerate(circuit.data):
        operations.append((inst, qargs, cargs))
        visited.append(index)
        if any(circuit.find_bit(q).index == i for q in qargs):
            check_list.append(index)
            last_op_index_i = index
        if any(circuit.find_bit(q).index == j for q in qargs):
            get_list.append(index)
            

    # Create a new circuit with the same registers
    new_circuit = QuantumCircuit(*circuit.qregs, *circuit.cregs)

    # Add operations up to the last operation of qubit i
    for index, (inst, qargs, cargs) in enumerate(operations):
        # if isinstance(inst, Measure) and any(circuit.find_bit(q).index == j for q in qargs):
        #     continue
        print(index, list(circuit.find_bit(q).index for q in qargs))    
        if index <= last_op_index_i and all(circuit.find_bit(q).index != j for q in qargs):
            new_circuit.append(inst, qargs, cargs)
            visited.remove(index)
        if index == last_op_index_i:
            # Insert measurement and reset for qubit i
            #new_circuit.measure(i, 0)
            new_circuit.append(Reset(), [i], []).c_if(new_circuit.cregs[0], 1)
            
    # print(check_list)
    # for index, (inst, qargs, cargs) in enumerate(operations):
    #     if index <= last_op_index_i and all(circuit.find_bit(q).index == j for q in qargs):
    #         new_qargs = [new_circuit.qubits[i] if circuit.find_bit(q).index == j else q for q in qargs]
    #         new_circuit.append(inst, new_qargs, cargs)
        

    # Process remaining operations, replacing qubit j with qubit i
    for index, (inst, qargs, cargs) in enumerate(operations):
        # print(operations[index])
        '''if isinstance(inst, Measure) and any(circuit.find_bit(q).index == j for q in qargs):
            continue'''
        if  index in get_list:
            new_qargs = [new_circuit.qubits[i] if circuit.find_bit(q).index == j else q for q in qargs]
            new_circuit.append(inst, new_qargs, cargs)
            visited.remove(index)
    for index, (inst, qargs, cargs) in enumerate(operations):
        if index in visited:
            new_circuit.append(inst, qargs, cargs)
            visited.remove(index)
    # print(f'there is remain {visited} gates')

    return remove_consecutive_duplicate_gates(new_circuit)