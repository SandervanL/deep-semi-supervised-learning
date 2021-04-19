# Retrieve subscription ID from environment variable.
import time
from dataclasses import dataclass
from typing import List, Optional
from os import environ

from azure.identity import ClientSecretCredential

from runtests.CredentialWrapper import CredentialWrapper
from runtests.ExecutionEnvironment import ExecutionEnvironment
from runtests.VirtualMachine import VirtualMachine


@dataclass
class TestConfig:
    n_labels: int
    n_hidden: int


USERNAME = environ['AZURE_USER']
PASSWORD = environ['AZURE_PWD']

credentials = CredentialWrapper()
subscription_id = environ['AZURE_SESSION_ID']

resource_group_name = "DeepLearning"
virtual_network_name = "deeplearning-vnet"
subnet_name = "deeplearning-subnet"
security_group_name = "deeplearning-security"
security_rule_name = "deeplearning-ssh-rule"

execution_envs: List[ExecutionEnvironment] = []

locations = [
    "westeurope",
    "centralus",
    'australiaeast',
    'brazilsouth',
    'japaneast',
    'northuk',
    'centralkorea',
    'westus',
]

with open('start_server_project.sh') as file:
    first_init_script = file.read()

with open('start_server_conda.sh') as file:
    second_init_script = file.read()

with open('C:\\Users\\sande\\.ssh\\azure_deeplearning.pub') as file:
    ssh_public_key = file.read()

ssh_private_key_path = 'C:\\Users\\sande\\.ssh\\azure_deeplearning'

print("Loaded SSH public key & init scripts.")

test_configs = [TestConfig(n_labels, 300) for n_labels in [100, 600, 1000, 3000] for _ in range(2)]
# [TestConfig(600, n_hidden) for n_hidden in [100, 300, 600, 1000]]
# test_configs = [TestConfig(100, 500)]

virtual_machines: List[Optional[VirtualMachine]] = [None]


with open('machines.csv', 'w') as file:
    file.write('region,n_labels,n_hidden,ip')
# test_configs = [TestConfig(n_labels, 300) for n_labels in [100, 600, 1000, 3000] for _ in range(2)]
test_configs = [TestConfig(600, n_hidden) for n_hidden in [100, 300, 600, 1000] for _ in range(2)]

virtual_machines: List[Optional[VirtualMachine]] = [None]

print(f"Creating {len(test_configs)} resource groups.")
for i, test_config in enumerate(test_configs):
    execution_env = ExecutionEnvironment(credentials, subscription_id)

    print(f"Creating resource group {i + 1}: {resource_group_name}-{locations[i]}westeurope.")
    execution_env.get_or_create_resource_group(f"{resource_group_name}-{locations[i]}")

    print(f"Creating virtual network {i + 1}: {virtual_network_name}-{locations[i]}")
    execution_env.get_or_create_virtual_network(f"{virtual_network_name}-{locations[i]}")

    print(f"Creating subnet {i + 1}: {subnet_name}-{locations[i]}")
    execution_env.get_or_create_subnet(f"{subnet_name}-{locations[i]}")

    print(f"Creating security group {i + 1}: {security_group_name}-{locations[i]}")
    execution_env.get_or_create_security_group(f"{security_group_name}-{locations[i]}")

    print(f"Creating security SSH rule {i + 1}: {security_rule_name}-{locations[i]}")
    execution_env.get_or_create_ssh_security_rule(f"{security_rule_name}-{locations[i]}")

    print(
        f"Creating Virtual Machine {i + 1} in {locations[i]} running {test_config.n_labels} labels and {test_config.n_hidden} hidden nodes.")
    virtual_machine = VirtualMachine(execution_env, locations[i])

    print(f"Creating IP address.")
    virtual_machine.set_ip(f'deep-learning-{test_config.n_labels}-{test_config.n_hidden}-{i}-ip')
    with open('machines.csv', 'a') as file:
        file.write(f"{locations[i]},{test_config.n_labels},{test_config.n_hidden},{virtual_machine.ip.ip_address}")

    time.sleep(10)

    print(f"Creating IP config.")
    virtual_machine.set_network_interface(
        f'deep-learning-{test_config.n_labels}-{test_config.n_hidden}-{i}-ipconfig')

    print(f"Starting virtual machine.")
    virtual_machine.start_virtual_machine(
        f'deep-learning-{locations[i]}-{test_config.n_labels}-{test_config.n_hidden}-{i}-vm',
        USERNAME,
        PASSWORD,
        ssh_public_key
    )

    print(f"Opening SSH connection.")
    virtual_machine.open_ssh(ssh_private_key_path)

    print(f"Running first init script.")
    virtual_machine.run_command(first_init_script)

    print("Reopening SSH connection.")
    virtual_machine.close_ssh()
    virtual_machine.open_ssh(ssh_private_key_path)

    # print(f"Running second init script.")
    # virtual_machine.run_command(second_init_script)

    print(f"Running test.")
    virtual_machine.run_test(test_config.n_labels, test_config.n_hidden)

    virtual_machines.append(virtual_machine)
