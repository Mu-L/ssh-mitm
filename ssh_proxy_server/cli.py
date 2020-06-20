from enhancements.modules import ModuleParser
from enhancements.plugins import LogModule

from paramiko import Transport

from ssh_proxy_server.server import SSHProxyServer

from ssh_proxy_server.authentication import (
    Authenticator,
    AuthenticatorPassThrough
)
from ssh_proxy_server.interfaces import (
    BaseServerInterface,
    ServerInterface
)
from ssh_proxy_server.forwarders import (
    BaseForwarder,
    SCPBaseForwarder,
    SCPForwarder,
    SSHBaseForwarder,
    SSHForwarder,
    SFTPBaseHandle,
    SFTPForwardHandle
)


def main():
    parser = ModuleParser(description='SSH Proxy Server', baseclass=BaseForwarder, modules_from_file=True)

    parser.add_plugin(LogModule)

    parser.add_argument(
        '--listen-address',
        dest='listen_address',
        default='127.0.0.1',
        help='listen port'
    )
    parser.add_argument(
        '--listen-port',
        dest='listen_port',
        default=10022,
        type=int,
        help='listen port'
    )

    parser.add_module(
        '--ssh-interface',
        dest='ssh_interface',
        default=SSHForwarder,
        help='ProxyManager to manage the Proxy',
        baseclass=SSHBaseForwarder
    )
    parser.add_module(
        '--scp-interface',
        dest='scp_interface',
        default=SCPForwarder,
        help='ProxyManager to manage the Proxy',
        baseclass=SCPBaseForwarder
    )
    parser.add_module(
        '--sftp-handler',
        dest='sftp_handler',
        default=SFTPForwardHandle,
        help='SFTP Handler to handle sftp file transfers',
        baseclass=SFTPBaseHandle
    )
    parser.add_module(
        '--server-interface',
        dest='auth_interface',
        default=ServerInterface,
        baseclass=BaseServerInterface,
        help='interface for authentication'
    )
    parser.add_module(
        '--authenticator',
        dest='authenticator',
        default=AuthenticatorPassThrough,
        baseclass=Authenticator,
        help='module for user authentication'
    )
    parser.add_argument(
        '--forward-agent',
        dest='foreward_agent',
        action='store_true',
        help='enables agent forwarding'
    )
    parser.add_argument(
        '--banner-name',
        dest='banner_name',
        help='set a custom string as server banner'
    )

    args = parser.parse_args()

    args.authenticator.AGENT_FORWARDING = args.foreward_agent

    proxy = SSHProxyServer(
        (args.listen_address, args.listen_port),
        ssh_interface=args.ssh_interface,
        scp_interface=args.scp_interface,
        sftp_handler=args.sftp_handler,
        authentication_interface=args.auth_interface,
        authenticator=args.authenticator
    )
    if args.banner_name is not None:
        Transport._CLIENT_ID = args.banner_name
    proxy.start()
