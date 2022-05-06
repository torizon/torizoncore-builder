"""Helper functions and classes for working with a SOTA server."""

import json
import logging

from zipfile import ZipFile

from urllib.parse import urlparse, urlunparse
from oauthlib.oauth2 import BackendApplicationClient
from requests_oauthlib import OAuth2Session

log = logging.getLogger("torizon." + __name__)


# pylint: disable=too-many-instance-attributes
class ServerCredentials:
    """Class representing the information required for accessing the OTA server.

    Information includes the URLs for authentication and for fetching
    metadata, along with the required credentials (items that are found
    in the 'credentials.zip' file obtained from the OTA server.
    """

    def __init__(self, credentials):
        self.credentials_fname = credentials
        self.treehub_ = None
        self.repo_url_ = None
        # Derived data:
        self.method_ = None
        self.ostree_server_ = None
        self.auth_server_ = None
        self.client_id_ = None
        self.client_secret_ = None
        self.scope_ = None
        self.provision_raw_ = None
        self._load()

    def _load(self):
        fname = self.credentials_fname
        with ZipFile(fname, "r") as archive:
            for item in archive.filelist:
                if item.filename == "treehub.json":
                    log.debug(f"Loading '{item.filename}' from '{fname}'")
                    self.treehub_ = json.loads(archive.read(item).decode("utf-8"))
                    log.debug(f"treehub data: {self.treehub_}")

                elif item.filename == "client_auth.p12":
                    assert False, "client_auth.p12 is not currently handled"

                elif item.filename == "tufrepo.url":
                    log.debug(f"Loading '{item.filename}' from '{fname}'")
                    self.repo_url_ = archive.read(item).decode("utf-8").strip()
                    log.debug(f"repo_url: '{self.repo_url_}'")

                elif item.filename == "provision.json":
                    log.debug(f"Loading '{item.filename}' from '{fname}'")
                    self.provision_raw_ = archive.read(item)
                    log.debug(f"provision data (raw): {self.provision_raw_}")

        # Fill in derived data:
        self._parse_treehub()

    def _parse_treehub(self):
        if "oauth2" in self.treehub_:
            self.method_ = "oauth2"
            self.auth_server_ = self.treehub_["oauth2"]["server"]
            self.client_id_ = self.treehub_["oauth2"]["client_id"]
            self.client_secret_ = self.treehub_["oauth2"]["client_secret"]
            self.scope_ = self.treehub_["oauth2"].get("scope")
        else:
            assert False, \
                "Currently we support only OAuth2 authentication/authorization"

        assert "ostree" in self.treehub_, \
            "ostree key must exist in treehub metadata"
        self.ostree_server_ = self.treehub_["ostree"].get("server")

    @property
    def repo_url(self):
        """Base URL for the image repo endpoints (always without a slash at the end)"""
        assert self.repo_url_ is not None
        return self.repo_url_.rstrip("/")

    @property
    def director_url(self):
        """Base URL for the director repo endpoints (based on the repo URL)

        A repo_url of
        'https://api-pilot.torizon.io/a/b/c/d/' becomes
        'https://api-pilot.torizon.io/director/'
        """
        assert self.repo_url_ is not None
        parts = urlparse(self.repo_url_)
        parts = parts._replace(path="/director")
        return urlunparse(parts)

    @property
    def method(self):
        """Method to be used to get authorization to access the OTA server

        Currently this will return "oauth2" always.
        """
        return self.method_

    @property
    def ostree_server(self):
        """URL to the OSTree server for the user (at TreeHub)"""
        return self.ostree_server_

    @property
    def auth_server(self):
        """URL to the authentication/authorization service endpoint"""
        return self.auth_server_

    @property
    def client_id(self):
        """client_id field for OAuth2"""
        return self.client_id_

    @property
    def client_secret(self):
        """client_id field for OAuth2"""
        return self.client_secret_

    @property
    def scope(self):
        """scope field for OAuth2"""
        return self.scope_

    @property
    def provision_raw(self):
        """Provisioning raw data"""
        return self.provision_raw_

    @property
    def provision(self):
        """Provisioning data"""
        if self.provision_raw_:
            return json.loads(self.provision_raw_.decode("utf-8"))
        return None

    def __str__(self):
        """Get string representation of instance"""
        fields = ["method_", "auth_server_", "client_id_", "client_secret_", "scope_",
                  "repo_url_", "ostree_server_"]
        values = [getattr(self, field) for field in fields]
        parts = []
        for field, value in zip(fields, values):
            parts.append(f"{field}: {value}")
        return "ServerCredentials: {" + ", ".join(parts) + "}"
# pylint: enable=too-many-instance-attributes


def get_access_token(server_creds):
    """Get the access token (bearer token) from the authorization server

    Services requiring authorization would accept a request only if the
    access token is sent to them via the "Authorization" header which
    would be formatted like this: 'Authorization: Bearer {access_token}'.
    """

    assert server_creds.method == "oauth2", \
        "get_access_token() can only be used with OAuth2"
    assert server_creds.client_id, \
        "Cannot fetch access token to SOTA server: client_id not set"
    assert server_creds.client_secret, \
        "Cannot fetch access token to SOTA server: client_secret not set"

    # See https://requests-oauthlib.readthedocs.io/en/latest/oauth2_workflow.html
    client = BackendApplicationClient(client_id=server_creds.client_id)
    oauth = OAuth2Session(client=client, scope=server_creds.scope)
    token = oauth.fetch_token(
        token_url=f"{server_creds.auth_server}/token",
        client_id=server_creds.client_id,
        client_secret=server_creds.client_secret)
    return token["access_token"]

# EOF
