# Import the needed credential and management objects from the libraries.
import socket
import time
from typing import Optional
from os import system

import paramiko
from azure.mgmt.compute import ComputeManagementClient
from paramiko.buffered_pipe import PipeTimeout
from paramiko.client import SSHClient

from runtests.ExecutionEnvironment import ExecutionEnvironment


class VirtualMachine():
    def __init__(self, execution_env: ExecutionEnvironment, location: str):
        self.execution_env = execution_env
        self.compute_client = ComputeManagementClient(execution_env.credential, execution_env.subscription_id)
        self.location = location
        self.ip = None
        self.nic = None
        self.ssh_security_rule_name = None
        self.ssh_security_rule = None
        self.username = None
        self.password = None
        self.virtual_machine = None
        self.ssh: Optional[SSHClient] = None

    def set_ip(self, ip_name: str):
        try:
            self.ip = self.execution_env.network_client.public_ip_addresses.get(self.execution_env.group_name, ip_name)
        except Exception:
            poller = self.execution_env.network_client.public_ip_addresses.create_or_update(
                self.execution_env.group_name,
                ip_name,
                {
                    "location": self.location,
                    "sku": {"name": "Standard"},
                    "public_ip_allocation_method": "Static",
                    "public_ip_address_version": "IPV4"
                })
            self.ip = poller.result()

    def set_network_interface(self, nic_name: str):
        try:
            self.nic = self.execution_env.network_client.network_interfaces.get(self.execution_env.group_name, nic_name)
        except Exception:
            poller = self.execution_env.network_client.network_interfaces.create_or_update(
                self.execution_env.group_name,
                nic_name,
                {
                    "location": self.location,
                    "ip_configurations": [{
                        "name": nic_name,
                        "subnet": {"id": self.execution_env.subnet.id},
                        "public_ip_address": {"id": self.ip.id}
                    }],
                    "networkSecurityGroup": {
                        "id": self.execution_env.security_group.id,
                    },
                }
            )

            self.nic = poller.result()

    def start_virtual_machine(self, virtual_machine_name: str, username: str, password: str, ssh_public_key: str):
        self.username = username
        self.password = password
        poller = self.compute_client.virtual_machines.create_or_update(
            self.execution_env.group_name,
            virtual_machine_name,
            {
                "location": self.location,
                "storage_profile": {
                    "image_reference": {
                        "publisher": 'Canonical',
                        "offer": "UbuntuServer",
                        "sku": "18.04-LTS",
                        "version": "latest"
                    }
                },
                "hardware_profile": {
                    "vm_size": "Standard_DS3_v2"
                },
                "os_profile": {
                    "computer_name": virtual_machine_name,
                    "admin_username": username,
                    "admin_password": password
                },
                "network_profile": {
                    "network_interfaces": [{
                        "id": self.nic.id,
                    }]
                },
                "ssh": {
                    "publicKeys": [{
                        "path": f"/home/{username}/.ssh/authorized_keys",
                        "keyData": ssh_public_key,
                    }]
                }
            }
        )

        self.virtual_machine = poller.result()
        self.execution_env.virtual_machines.append(self)

    def close_ssh(self):
        self.ssh.close()

    def open_ssh(self, private_key_path: str):
        self.ssh = paramiko.SSHClient()
        self.ssh.load_system_host_keys()
        self.ssh.set_missing_host_key_policy(paramiko.WarningPolicy())
        pk = paramiko.RSAKey.from_private_key(open(private_key_path))
        for i in range(3):
            try:
                self.ssh.connect(self.ip.ip_address, port=22, username=self.username, password=self.password, pkey=pk)
                break
            except Exception as e:
                print(e)
                time.sleep(5)

    def run_command(self, command: str):
        print(f"Executing command: {command}")
        stdin, stdout, stderr = self.ssh.exec_command(command)
        if len(stderr.read()) > 0:
            try:
                print(stdout.read())
                print(stderr.read())
            except PipeTimeout:
                print("PipeTimeout")
            except socket.timeout:
                print("Socket timeout")

    def run_test(self, n_labels: int, n_hidden: int):
        self.run_command(f'tmux new-session -d -s training \'cd ~/deep-semi-supervised-learning && export ML_DATA_PATH="$HOME/deep-semi-supervised-learning/data" && export PATH="$HOME/anaconda3/condabin:$PATH" && conda create -n deeplearning python=3.8 -y && conda activate deeplearning && conda install numpy matplotlib theano scipy -yconda activate deeplearning && conda install numpy matplotlib theano scipy -y && python ~/deep-semi-supervised-learning/run_2layer_ssl.py {n_labels} 1000 {n_hidden}\'')
        system(f"start cmd /K ssh -i C:\\Users\\sande\\.ssh\\azure_deeplearning.pub sander_tud@{self.ip.ip_address} 'tmux attach-session -t training'")
