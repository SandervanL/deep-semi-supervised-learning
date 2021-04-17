import azure
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.v2020_04_01.models import NetworkSecurityGroup, SecurityRuleAccess, SecurityRuleDirection, \
    SecurityRuleProtocol
from azure.mgmt.resource import ResourceManagementClient
from msrest.authentication import BasicTokenAuthentication


class ExecutionEnvironment:
    def __init__(self, credential: BasicTokenAuthentication, subscription_id: str):
        self.credential = credential
        self.subscription_id = subscription_id

        self.resource_client = ResourceManagementClient(credential, subscription_id)
        self.network_client = NetworkManagementClient(credential, subscription_id)

        self.resource_group = None
        self.group_name = None
        self.location = None

        self.virtual_network = None
        self.virtual_network_name = None

        self.subnet = None
        self.subnet_name = None
        self.virtual_machines = []

        self.security_group_name = None
        self.security_group = None

        self.ssh_security_rule_name = None
        self.ssh_security_rule = None

    def get_or_create_resource_group(self, group_name: str, location: str = 'centralus'):
        self.group_name = group_name
        self.location = location
        try:
            self.resource_group = self.resource_client.resource_groups.get(group_name)
        except Exception:
            self.resource_group = self.resource_client.resource_groups.create_or_update(
                group_name, {"location": location})

    def get_or_create_virtual_network(self, vnet_name: str):
        self.virtual_network_name = vnet_name
        try:
            self.virtual_network = self.network_client.virtual_networks.get(self.group_name, vnet_name)
        except Exception:
            poller = self.network_client.virtual_networks.create_or_update(self.group_name, vnet_name,
                                                                           {
                                                                               "location": self.location,
                                                                               "address_space": {
                                                                                   "address_prefixes": ["10.0.0.0/16"]
                                                                               }
                                                                           })
            self.virtual_network = poller.result()

    def get_or_create_subnet(self, subnet_name: str):
        self.subnet_name = subnet_name
        try:
            self.subnet = self.network_client.subnets.get(self.group_name, self.virtual_network_name, self.subnet_name)
        except Exception:
            poller = self.network_client.subnets.create_or_update(
                self.group_name, self.virtual_network_name, subnet_name, {"address_prefix": "10.0.0.0/24"})
            self.subnet = poller.result()

    def get_or_create_security_group(self, security_group_name: str):
        self.security_group_name = security_group_name
        try:
            self.security_group = self.network_client.network_security_groups.get(self.group_name, security_group_name)
        except Exception:
            security_group_params = NetworkSecurityGroup(
                id="testnsg",
                location=self.location,
                tags={"name": security_group_name}
            )
            poller = self.network_client.network_security_groups.create_or_update(
                self.group_name,
                self.security_group_name,
                parameters=security_group_params
            )
            self.security_group = poller.result()

    def get_or_create_ssh_security_rule(self, rule_name: str):
        self.ssh_security_rule_name = rule_name
        try:
            self.ssh_security_rule = self.network_client.security_rules.get(self.group_name, rule_name)
        except Exception:
            poller = self.network_client.security_rules.create_or_update(
                self.group_name,
                self.security_group_name,
                self.ssh_security_rule_name,
                {
                    'access': SecurityRuleAccess.allow,
                    'description': 'SSH security rule',
                    'destination_address_prefix': '*',
                    'destination_port_range': '22',
                    'direction': SecurityRuleDirection.inbound,
                    'priority': 400,
                    'protocol': SecurityRuleProtocol.tcp,
                    'source_address_prefix': '*',
                    'source_port_range': '*',
                }
            )
            self.ssh_security_rule = poller.result()
