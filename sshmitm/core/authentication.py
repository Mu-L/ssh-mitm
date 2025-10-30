import logging
import sys
from abc import abstractmethod
from typing import TYPE_CHECKING, List, Optional

import paramiko
from colored.colored import attr, fg  # type: ignore[import-untyped]
from paramiko import PKey

from sshmitm.core.clients.ssh import AuthenticationMethod, SSHClient
from sshmitm.core.exceptions import MissingHostException
from sshmitm.core.logger import Colors
from sshmitm.moduleparser import BaseModule

if TYPE_CHECKING:
    import sshmitm


class RemoteCredentials:
    """
    The `RemoteCredentials` class represents the credentials required to access a remote host.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        username: str,
        password: Optional[str] = None,
        key: Optional[PKey] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """
        The `__init__` method is the constructor of the class and it is used to initialize the attributes of the class.

        :param username: (str) a string representing the username of the remote host. This is a required argument and must be specified when creating an instance of the class.
        :param password: (str) an optional string representing the password of the remote host. This argument is optional and if not specified, the value will be `None`.
        :param key: (PKey) an optional `PKey` object representing a private key used to authenticate with the remote host. This argument is optional and if not specified, the value will be `None`.
        :param host: (str) an optional string representing the hostname or IP address of the remote host. This argument is optional and if not specified, the value will be `None`.
        :param port: (int) an optional integer representing the port number used to connect to the remote host. This argument is optional and if not specified, the value will be `None`.
        """
        self.username: str = username
        """
        (str) a string representing the username of the remote host.
        """

        self.password: Optional[str] = password
        """
        (str) an optional string representing the password of the remote host. This argument is optional and if not specified, the value will be `None`.
        """

        self.key: Optional[PKey] = key
        """
        (PKey) an optional `PKey` object representing a private key used to authenticate with the remote host. This argument is optional and if not specified, the value will be `None`.
        """

        self.host: Optional[str] = host
        """
        (str) an optional string representing the hostname or IP address of the remote host. This argument is optional and if not specified, the value will be `None`.
        """

        self.port: Optional[int] = port
        """
        (int) an optional integer representing the port number used to connect to the remote host. This argument is optional and if not specified, the value will be `None`.
        """

    @staticmethod
    def load_private_key(path: str, passphrase: Optional[str] = None) -> paramiko.PKey:
        """
        Loads an OpenSSH private key from a file and returns a Paramiko PKey object.

        :param path: Path to the private key file (e.g., ~/.ssh/id_ed25519)
        :param passphrase: Optional password for encrypted keys
        :return: Instance of paramiko.PKey (e.g., RSAKey, Ed25519Key, ECDSAKey)
        :raises: paramiko.ssh_exception.SSHException for invalid or unknown key format
        """
        with open(path, "r", encoding="utf-8") as f:
            f.read()

        for key_cls in [
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
            paramiko.RSAKey,
        ]:
            try:
                return key_cls.from_private_key_file(path, password=passphrase)
            except (  # noqa: PERF203 # `try`-`except` within a loop incurs performance overhead
                paramiko.SSHException
            ):
                continue

        msg = "Unbekanntes oder ungültiges Schlüsselformat."
        raise paramiko.SSHException(msg)


class Authenticator(BaseModule):
    """Options for remote authentication."""

    REQUEST_AGENT_BREAKIN = False
    """
    This flag indicates if SSH-MITM should do a breakin to the client's ssh agent, even in cases where the agent is not forwarded.
    """

    @classmethod
    def parser_arguments(cls) -> None:
        """
        Adds the options for remote authentication using argparse.
        """
        plugin_group = cls.argument_group()
        plugin_group.add_argument(
            "--remote-host",
            dest="remote_host",
            help="remote host to connect to (default 127.0.0.1)",
        )
        plugin_group.add_argument(
            "--remote-port",
            type=int,
            dest="remote_port",
            help="remote port to connect to (default 22)",
        )
        plugin_group.add_argument(
            "--remote-fingerprints",
            type=str,
            dest="remote_fingerprints",
            help="comma-separated fingerprints; empty disables check",
        )
        plugin_group.add_argument(
            "--disable-remote-fingerprint-warning",
            dest="disable_remote_fingerprint_warning",
            action="store_true",
            help="disables the warning if no remote fingerprints are provided",
        )
        plugin_group.add_argument(
            "--auth-username",
            dest="auth_username",
            help="username for remote authentication",
        )
        plugin_group.add_argument(
            "--auth-password",
            dest="auth_password",
            help="password for remote authentication",
        )
        plugin_group.add_argument(
            "--auth-key",
            dest="auth_key",
            help="ssh private key for remote authentication",
        )

        plugin_group.add_argument(
            "--hide-credentials",
            dest="auth_hide_credentials",
            action="store_true",
            help="do not log credentials (usefull for presentations)",
        )

        honeypot_group = cls.argument_group(
            "AuthenticationFallback",
            description=("Options for the authentication fallback to a honey pot"),
        )
        honeypot_group.add_argument(
            "--enable-auth-fallback",
            action="store_true",
            help="enabled the fallback to a hoenypot when authentication not possible",
        )
        honeypot_group.add_argument(
            "--fallback-host",
            dest="fallback_host",
            required="--enable-auth-fallback" in sys.argv,
            help="fallback host for the honeypot",
        )
        honeypot_group.add_argument(
            "--fallback-port",
            dest="fallback_port",
            type=int,
            help="fallback port for the honeypot",
        )
        honeypot_group.add_argument(
            "--fallback-username",
            dest="fallback_username",
            required="--enable-auth-fallback" in sys.argv,
            help="username for the honeypot",
        )
        honeypot_group.add_argument(
            "--fallback-password",
            dest="fallback_password",
            required="--enable-auth-fallback" in sys.argv,
            help="password for the honeypot",
        )

    def __init__(self, session: "sshmitm.core.session.Session") -> None:
        """
        Initializes Authenticator instance.

        This class pass the authentication from the client to the server.

        :param session: an object of sshmitm.core.session.Session class to store session information.
        """
        super().__init__()
        self.session = session
        self.session.register_session_thread()

    def get_remote_host_credentials(
        self, username: str, password: Optional[str] = None, key: Optional[PKey] = None
    ) -> RemoteCredentials:
        """
        Get the credentials for remote host.

        :param username: remote host username.
        :param password: remote host password.
        :param key: remote host private key.
        :return: an object of RemoteCredentials class.
        """
        if self.args.auth_key:
            key = RemoteCredentials.load_private_key(self.args.auth_key)
        if self.session.proxyserver.transparent:
            return RemoteCredentials(
                username=self.args.auth_username or username,
                password=self.args.auth_password or password,
                key=key,
                host=self.args.remote_host or self.session.socket_remote_address[0],
                port=self.args.remote_port or self.session.socket_remote_address[1],
            )
        return RemoteCredentials(
            username=self.args.auth_username or username,
            password=self.args.auth_password or password,
            key=key,
            host=self.args.remote_host or "127.0.0.1",
            port=self.args.remote_port or 22,
        )

    @abstractmethod
    def get_auth_methods(
        self, host: str, port: int, username: Optional[str] = None
    ) -> Optional[List[str]]:
        """
        Get the available authentication methods for a remote host.

        :param host: remote host address.
        :param port: remote host port.
        :param username: username which is used during authentication
        :return: a list of strings representing the available authentication methods.
        """

    def authenticate(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        key: Optional[PKey] = None,
        store_credentials: bool = True,
    ) -> int:
        """
        Authenticate with the remote host using provided credentials.

        :param username: remote host username.
        :param password: remote host password.
        :param key: remote host private key.
        :param store_credentials: boolean flag to indicate if provided credentials should be stored.
        :return: integer representing authentication success or failure.
        """
        if store_credentials:
            self.session.username_provided = username
            self.session.password_provided = password
        if username:
            remote_credentials: RemoteCredentials = self.get_remote_host_credentials(
                username, password, key
            )
            self.session.username = remote_credentials.username
            self.session.password = remote_credentials.password
            self.session.remote_key = remote_credentials.key
            self.session.remote_address = (
                remote_credentials.host,
                remote_credentials.port,
            )
        if key and not self.session.remote_key:
            self.session.remote_key = key

        if (
            self.session.remote_address[0] is None
            or self.session.remote_address[1] is None
        ):
            logging.error("no remote host")
            return paramiko.common.AUTH_FAILED

        try:
            if self.session.agent:
                return self.auth_agent(
                    self.session.username,
                    self.session.remote_address[0],
                    self.session.remote_address[1],
                )
            if self.session.password:
                return self.auth_password(
                    self.session.username,
                    self.session.remote_address[0],
                    self.session.remote_address[1],
                    self.session.password,
                )
            if self.session.remote_key:
                return self.auth_publickey(
                    self.session.username,
                    self.session.remote_address[0],
                    self.session.remote_address[1],
                    self.session.remote_key,
                )
        except MissingHostException:
            logging.error("no remote host")
        except Exception:  # pylint: disable=broad-exception-caught
            logging.exception("internal error, abort authentication!")
        return paramiko.common.AUTH_FAILED

    @abstractmethod
    def auth_agent(self, username: str, host: str, port: int) -> int:
        """
        Performs authentication using the ssh-agent.
        """

    @abstractmethod
    def auth_password(self, username: str, host: str, port: int, password: str) -> int:
        """
        Performs authentication using a password.
        """

    @abstractmethod
    def auth_publickey(self, username: str, host: str, port: int, key: PKey) -> int:
        """
        Performs authentication using public key authentication.
        """

    def auth_fallback(self, username: str) -> int:
        """
        This method is executed when the intercepted client would be allowed to log in to the server,
        but due to the interception, the login is not possible.

        The method checks if a fallback host (a honeypot) has been provided and if not,
        it closes the session, and logs that authentication is not possible.
        If the fallback host has been provided, it attempts to log in to the honeypot using
        the username and password provided, and reports success or failure accordingly.
        If authentication against the honeypot fails, it logs an error message.
        """
        if not self.args.fallback_host:
            if self.session.agent:
                logging.error(
                    "\n".join(
                        [
                            Colors.stylize(
                                Colors.emoji("exclamation")
                                + " ssh agent keys are not allowed for signing. Remote authentication not possible.",
                                fg("red") + attr("bold"),
                            ),
                            Colors.stylize(
                                Colors.emoji("information")
                                + " To intercept clients, you can provide credentials for a honeypot.",
                                fg("yellow") + attr("bold"),
                            ),
                        ]
                    )
                )
            else:
                logging.error(
                    "\n".join(
                        [
                            Colors.stylize(
                                Colors.emoji("exclamation")
                                + " ssh agent not forwarded. Login to remote host not possible with publickey authentication.",
                                fg("red") + attr("bold"),
                            ),
                            Colors.stylize(
                                Colors.emoji("information")
                                + " To intercept clients without a forwarded agent, you can provide credentials for a honeypot.",
                                fg("yellow") + attr("bold"),
                            ),
                        ]
                    )
                )
            return paramiko.common.AUTH_FAILED

        auth_status = self.connect(
            user=self.args.fallback_username or username,
            password=self.args.fallback_password,
            host=self.args.fallback_host,
            port=self.args.fallback_port,
            method=AuthenticationMethod.PASSWORD,
            run_post_auth=False,
        )
        if auth_status == paramiko.common.AUTH_SUCCESSFUL:
            logging.warning(
                Colors.stylize(
                    Colors.emoji("warning")
                    + " publickey authentication failed - no agent forwarded - connecting to honeypot!",
                    fg("yellow") + attr("bold"),
                ),
            )
        else:
            logging.error(
                Colors.stylize(
                    Colors.emoji("exclamation")
                    + " Authentication against honeypot failed!",
                    fg("red") + attr("bold"),
                ),
            )
        return auth_status

    def connect(  # pylint: disable=too-many-arguments
        self,
        user: str,
        host: str,
        port: int,
        method: AuthenticationMethod,
        password: Optional[str] = None,
        key: Optional[PKey] = None,
        *,
        run_post_auth: bool = True,
    ) -> int:
        """
        Connects to the SSH server and performs the necessary authentication.
        """
        if not host:
            raise MissingHostException

        auth_status = paramiko.common.AUTH_FAILED
        with self.session.ssh_client_created:
            self.session.ssh_client = SSHClient(
                host,
                port,
                method,
                password,
                user,
                key,
                self.session,
                self.args.remote_fingerprints,
                self.args.disable_remote_fingerprint_warning,
            )
            self.pre_auth_action()
            try:
                if (
                    self.session.ssh_client is not None
                    and self.session.ssh_client.connect()
                ):
                    auth_status = paramiko.common.AUTH_SUCCESSFUL
            except paramiko.SSHException:
                logging.error(
                    Colors.stylize(
                        "Connection to remote server refused", fg("red") + attr("bold")
                    )
                )
                return paramiko.common.AUTH_FAILED
            if run_post_auth:
                self.post_auth_action(auth_status == paramiko.common.AUTH_SUCCESSFUL)
            self.session.ssh_client_auth_finished = True
            self.session.ssh_client_created.notify_all()
        return auth_status

    def pre_auth_action(self) -> None:
        """Perform any pre-authentication actions.

        This method is called before the authentication process starts.
        """

    def post_auth_action(self, success: bool) -> None:
        """Perform any post-authentication actions.

        This method is called after the authentication process is completed, whether successfully or not.

        :param success: indicates if the authentication was successful or not
        """

    def on_session_close(self) -> None:
        """Performs actions when the session is closed."""
