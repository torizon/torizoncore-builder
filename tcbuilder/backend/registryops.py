"""Helper functions and classes for working with Docker registries."""

import hashlib
import logging
import os
import re
from copy import deepcopy
from urllib.parse import urljoin

import requests
from requests.exceptions import RequestException
from requests.auth import HTTPBasicAuth
from tcbuilder.errors import TorizonCoreBuilderError, InvalidArgumentError, InvalidDataError

log = logging.getLogger("torizon." + __name__)

# As per https://docs.docker.com/engine/reference/commandline/tag/,
# default registry is "registry-1.docker.io".
# TODO: Determine why docker info shows "https://index.docker.io/"
DEFAULT_REGISTRY = "registry-1.docker.io"

MANIFEST_MEDIA_TYPE = "application/vnd.docker.distribution.manifest.v2+json"
MANIFEST_LIST_MEDIA_TYPE = "application/vnd.docker.distribution.manifest.list.v2+json"
DEFAULT_GET_MANIFEST_HEADERS = {
    "Accept": ("application/vnd.docker.distribution.manifest.list.v2+json,"
               "application/vnd.docker.distribution.manifest.v2+json")
}

SHA256_PREFIX = "sha256:"

# https://stackoverflow.com/questions/19512317/
# what-are-the-valid-characters-in-http-authorization-header
WWW_AUTH_TOKEN_CHARS = "-+!#$%&'*.0-9A-Za-z^_`|~"
WWW_AUTH_QUOTED_CHARS = "-+!#$%&'*.0-9A-Za-z^_`|~ (),/:;<=>?@\\\\\\[\\]{}"
WWW_AUTH_KEY_VALUE_UNQUOTED_RE = re.compile(
    "(?P<key>[" + WWW_AUTH_TOKEN_CHARS + "]+)=(?P<value>[" + WWW_AUTH_TOKEN_CHARS + "]+)")
WWW_AUTH_KEY_VALUE_QUOTED_RE = re.compile(
    "(?P<key>[" + WWW_AUTH_TOKEN_CHARS + "]+)=\"(?P<value>[" + WWW_AUTH_QUOTED_CHARS + "]+)\"")
WWW_AUTH_SCHEME_RE = re.compile(
    " *(?P<scheme>[" + WWW_AUTH_TOKEN_CHARS + "]+) *")
WWW_AUTH_ATTRIB_SEP_RE = re.compile("( *, *| *$)")

REGISTRY_REGEX = re.compile((r"^((?!.*://).*|[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})"
                             r"(:[0-9]*)?$"))


def parse_www_auth_header(header):
    """Basic parsing of the WWW-Authenticate HTTP header

    E.g. for the header:
    WWW-Authenticate: Bearer realm="https://auth.docker.io/token",
                             service="registry.docker.io",
                             scope="repository:samalba/my-app:pull,push"
    Output would be: (scheme, attributes), where
    - scheme="Bearer";
    - attributes=[("realm", "https://auth.docker.io/token"),
                  ("service", "registry.docker.io"),
                  ("scope", "repository:samalba/my-app:pull,push")]

    :param header: Value of the WWW-Authenticate header to be parsed in the form
                   `scheme attr1=value1,attr2=value2,...
    :return: (scheme, attributes) where scheme is extracted verbatim from the header
             and attributes is a list of pairs (attr, value) representing the data in
             the header.
    """

    log.debug(f"WWW-Authenticate header='{header}'")
    scheme_match = WWW_AUTH_SCHEME_RE.match(header)
    assert scheme_match, "No scheme in header string '{header}'"
    scheme = scheme_match.group("scheme")
    current = header[scheme_match.end(0):]
    attribs = []
    try:
        while current:
            match = WWW_AUTH_KEY_VALUE_UNQUOTED_RE.match(current)
            if match:
                _key, _value = (match.group("key"), match.group("value"))
                attribs.append((_key, _value))
                current = current[match.end(0):]
                sep_match = WWW_AUTH_ATTRIB_SEP_RE.match(current)
                assert sep_match
                current = current[sep_match.end(0):]
                continue
            match = WWW_AUTH_KEY_VALUE_QUOTED_RE.match(current)
            if match:
                _key, _value = (match.group("key"), match.group("value"))
                # Replace \<CH> by just <CH>.
                _value = re.sub(r'\\(.)', r'\1', _value)
                attribs.append((_key, _value))
                current = current[match.end(0):]
                sep_match = WWW_AUTH_ATTRIB_SEP_RE.match(current)
                assert sep_match
                current = current[sep_match.end(0):]
                continue
            assert False

    except AssertionError:
        raise AssertionError(f"Failed to parse www-authenticate header at {current}")

    return scheme, attribs


class ParsedImageName:
    """"Output of parse_image_name()"""

    def __init__(self, registry, name, tag):
        assert not registry.endswith("/"), \
            "The registry name should not end with a slash"
        self.registry = registry
        self.name = name
        self.tag = tag

    def get_repo(self):
        """Determine repository from image name

        E.g. with name="linux/ubuntu:latest", output="linux"
        """
        comps = self.name.split("/")
        if len(comps) >= 2:
            return comps[0]
        return None

    def get_name_with_tag(self, include_registry=True):
        """Get name of the image including the tag or digest"""
        _tag = self.tag or "latest"
        separator = "@" if _tag.startswith(SHA256_PREFIX) else ":"

        if self.registry and include_registry:
            return f"{self.registry}/{self.name}{separator}{_tag}"

        return f"{self.name}{separator}{_tag}"

    def set_tag(self, tag, is_digest=True):
        if is_digest:
            # TODO: Add prefix if not present but string looks like a sha256.
            assert tag.startswith(SHA256_PREFIX), \
                f"Tag {tag} doesn't look like a digest"
        self.tag = tag

    def __repr__(self):
        return (f"ImageName(registry='{self.registry}', "
                f"name='{self.name}', tag='{self.tag}')")


def parse_image_name(image_name):
    """Parse an image name as per Docker image tagging specification

    As per https://docs.docker.com/engine/reference/commandline/tag/, an
    image name is made up of slash-separated name components, optionally
    prefixed by a registry hostname.

    >>> parse_image_name('http://localhost/ubuntu:latest')
    <Exception thrown>

    # Without a registry:
    >>> parse_image_name('ubuntu:latest')
    ImageName(registry='', name='ubuntu', tag='latest')
    >>> parse_image_name('linux/ubuntu:latest')
    ImageName(registry='', name='linux/ubuntu', tag='latest')
    >>> parse_image_name('localhost/ubuntu:latest@sha256:123456')
    ImageName(registry='', name='localhost/ubuntu:latest', tag='sha256:123456')

    # With a registry:
    >>> parse_image_name('localhost:8000/ubuntu:latest')
    ImageName(registry='localhost:8000', name='ubuntu', tag='latest')
    >>> parse_image_name('gcr.io/ubuntu:latest')
    ImageName(registry='gcr.io', name='ubuntu', tag='latest')
    """

    mres = re.match(r"^([a-zA-Z][-+.a-zA-Z0-9]+)://", image_name)
    if mres:
        raise TorizonCoreBuilderError(
            f"Image '{image_name}' is specifying a scheme which is not allowed.")

    registry = ""
    name_with_tag = image_name
    if "/" in image_name:
        comps = image_name.split("/", 1)
        # If the first part before the slash has a dot or a colon we assume it
        # is a server (registry) name.
        if "." in comps[0] or ":" in comps[0]:
            registry, name_with_tag = comps

    if "@" in name_with_tag:
        # E.g. ubuntu@sha256:1234...
        name, tag = name_with_tag.split("@")
    elif ":" in name_with_tag:
        # E.g. ubuntu:latest
        name, tag = name_with_tag.split(":")
    else:
        # E.g. ubuntu
        name, tag = name_with_tag, None

    return ParsedImageName(registry, name, tag)


def validate_registries(registries):
    if registries is None:
        return

    for registry in registries:
        if not REGISTRY_REGEX.match(registry[0]):
            raise InvalidArgumentError(
                f"Error: invalid registry specified: '{registry[0]}'; "
                "the registry can be specified as a domain name or an IP "
                "address possibly followed by :<port-number>")


def get_registry_url(registry, scheme):
    """Get the registry URL from the registry hostname:port

    >>> get_registry_url("https://10.0.0.1:8000/", "http")
    <Exception thrown>
    >>> get_registry_url("10.0.0.1", "http")
    'http://10.0.0.1/'
    >>> get_registry_url("10.0.0.1:8000", "http")
    'http://10.0.0.1:8000/'
    >>> get_registry_url("gitlab.com:8000/", "https")
    'https://gitlab.com:8000/'
    >>> get_registry_url("gitlab.com:8000/", "https")
    'https://gitlab.com:8000/'
    >>> get_registry_url("gitlab.com:8000/a/b/c", "https")
    'https://gitlab.com:8000/a/b/c/'
    """

    mres = re.match(r"^([a-zA-Z][-+.a-zA-Z0-9]+)://", registry)
    if mres:
        raise TorizonCoreBuilderError(
            f"Registry '{registry}' is specifying a scheme which is not allowed.")

    resurl = f"{scheme}://{registry}"
    if not resurl.endswith("/"):
        resurl += "/"

    return resurl


class RegistryOperations:
    """Class providing operations on a Docker registry"""

    LOGINS = []
    CACERTS = []

    @classmethod
    def set_logins(cls, logins):
        """Set the username/password for authenticating with registries

        :param logins: A list-like object where one element is a pair (username, password)
                       to be used with the default registry and the other items are 3-tuples
                       (registry, username, password) with authentication information to
                       be used with other registries.
        """

        validate_registries(logins)
        cls.LOGINS = logins.copy()

    @classmethod
    def get_logins(cls):
        """Get the list-like object 'LOGINS'."""
        return cls.LOGINS

    @classmethod
    def set_cacerts(cls, cacerts):
        """Set the cacert used in secure private registries

        :param cacerts: A list-like object where one element is a pair (REGISTRY, CACERT)
                        to be used with private secure registries.
        """
        validate_registries(cacerts)
        cls.CACERTS = cacerts.copy()
        for cacert in cls.CACERTS:
            cacert_path = os.path.abspath(cacert[1])
            if not os.path.isfile(cacert_path):
                raise InvalidArgumentError(
                    f"Error: CA certificate file '{cacert[1]}' must exist and be a file.")

            cacert[1] = cacert_path

    @classmethod
    def get_cacerts(cls):
        """Get the list-like object 'CACERTS'."""
        return cls.CACERTS

    def __init__(self, registry=None):
        self.registry = registry
        self.token_cache = {}
        self.cacert = None
        self.login = None
        self._setup_credentials()

    def _setup_credentials(self):
        """Set up the username/password and certificate to access the registry"""
        for _cacert in self.CACERTS:
            if _cacert[0] == self.registry:
                self.cacert = _cacert[1]

        for _login in self.LOGINS:
            if len(_login) == 2:
                username, password = _login
                if not self.registry or self.registry == DEFAULT_REGISTRY:
                    self.login = (username, password)
            elif len(_login) == 3:
                reg, username, password = _login
                if reg == self.registry:
                    self.login = (username, password)
            else:
                assert False, "Unhandled condition in _setup_credentials()"

        log.debug(f"Using certificate file '{self.cacert or 'None'}' and user name "
                  f"'{self.login[0] if self.login else 'None'}' to access registry "
                  f"'{self.registry}'")

    def _get_oauth2_token(self, attribs):
        """Get the OAuth2 token required for accessing some resources"""

        # --
        # Expected format (https://docs.docker.com/registry/spec/auth/token/):
        # Bearer realm="https://auth.docker.io/token",
        #        service="registry.docker.io",
        #        scope="repository:samalba/my-app:pull,push"
        # With scope being a space-separated list of scopes.
        # --

        # Helper function:
        def _consume_attrib(key, unique=True):
            nonlocal attribs
            values_ = []
            attribs_ = []
            for attr in attribs:
                if attr[0].lower() == key:
                    # Consume value.
                    values_.append(attr[1])
                else:
                    # Non-consumed pair.
                    attribs_.append(attr)
            attribs = attribs_
            if unique:
                if len(values_) != 1:
                    assert False, \
                        (f"Only one {key} can be defined in the WWW-Authenticate header "
                         f"({len(values_)} found)")
                return values_[0]
            return values_

        # Parse attributes:
        realm = _consume_attrib("realm")
        service = _consume_attrib("service")
        scope = _consume_attrib("scope")
        scopes = scope.split(" ")
        if attribs:
            log.warning(f"Attributes not processed in the WWW-Authenticate header: {attribs}")

        regurl = get_registry_url(self.registry or DEFAULT_REGISTRY, "https")
        auth_url = urljoin(regurl, realm)
        auth_parms = []
        auth_parms.append(("service", service))
        for scope in scopes:
            auth_parms.append(("scope", scope))

        # Request token to authorization end-point.
        assert regurl.startswith("https://"), \
            "This code needs review for dealing with Bearer token requests via HTTP."

        auth_login = None
        if self.login:
            log.debug("Using Basic Authentication credentials to access authorization end-point")
            auth_login = HTTPBasicAuth(*self.login)

        res = requests.get(auth_url, params=auth_parms, auth=auth_login)
        res_json = res.json()
        for scope in scopes:
            if "token" in res_json:
                self.token_cache[scope] = res_json["token"]
                continue
            log.debug(
                f"Could not get token for scope {scope}, registry {self.registry or 'default'}.")

    def _do_get_helper(self, url, repo_name, headers=None, send_auth_if_secure=False):
        headers = (headers or {}).copy()
        secure = url.startswith("https://")
        cacert = self.cacert if secure else None
        auth = None

        if send_auth_if_secure and secure:
            # Define Bearer (authorization) token for the request.
            scope = f"repository:{repo_name}:pull"
            if scope in self.token_cache:
                # If this scope is in the cache it means this end-point was accessed with a
                # Bearer token previously.
                log.debug(f"Using cached token for scope '{scope}'")
                headers.update({"Authorization": f"Bearer {self.token_cache[scope]}"})
            elif self.login:
                # Using Basic Authentication for the request.
                log.debug("Using Basic Authentication credentials")
                auth = HTTPBasicAuth(*self.login)
            else:
                log.debug(f"No token cached for scope {scope}")

        res = None
        try:
            res = requests.get(url, headers=headers, verify=cacert, auth=auth)
        except RequestException as exc:
            log.debug(f"GET '{url}' raised exception: {exc}")

        return res

    def _do_get(self, url, repo_name, headers=None):
        # Try initially without sending username/password.
        res = self._do_get_helper(url, repo_name, headers=headers, send_auth_if_secure=False)

        if res is not None and res.status_code == requests.codes["unauthorized"]:
            if "www-authenticate" in res.headers:
                auth_scheme, auth_attribs = parse_www_auth_header(res.headers["www-authenticate"])
                auth_scheme = auth_scheme.lower()

                # Determine the type of authentication being requested by the server.
                if auth_scheme == "basic":
                    if not self.login:
                        raise TorizonCoreBuilderError(
                            f"Error: registry {self.registry or DEFAULT_REGISTRY} requires"
                            " authentication but no credentials were provided.")
                    res = self._do_get_helper(
                        url, repo_name, headers=headers, send_auth_if_secure=True)

                elif auth_scheme == "bearer":
                    # Request and cache token before repeating the request.
                    self._get_oauth2_token(auth_attribs)
                    res = self._do_get_helper(
                        url, repo_name, headers=headers, send_auth_if_secure=True)

                else:
                    raise TorizonCoreBuilderError(
                        f"Error: registry {self.registry or DEFAULT_REGISTRY} uses "
                        f"authentication scheme '{auth_scheme}' which is not supported.")
            else:
                log.debug(f"GET to '{url}' got unauthorized but no www-authenticate header "
                          "was present in response.")

        return res

    def get_manifest(self, image_name, headers=None, ret_digest=False, val_digest=True):
        """Get the manifest of the specified image

        :param image_name: Name of the image such as ubuntu:latest or fedora/httpd:latest;
                           if the name contains a registry then it should match the one
                           specified in the constructor of the class.
        :param headers: Dict with extra headers to send to the server.
        :param ret_digest: Whether or not to return the digest of the manifest as part
                           of the function's output.
        :param val_digest: Whether or not to validate the digest of the manifest (only
                           relevant when the image name also specifies a digest, e.g.
                           "ubuntu@sha256:123123..."
        :return: (response, digest) if ret_digest=True or only the response otherwise.
        """

        headers = (headers or {}).copy()
        headers.update(DEFAULT_GET_MANIFEST_HEADERS)

        parsed_name = parse_image_name(image_name)

        if parsed_name.registry:
            assert parsed_name.registry == self.registry, \
                f"Internal error: passed in image name '{image_name}' does not match " \
                f"expected registry name '{self.registry}'."

        # Define name for building the manifest's URL. The default registry (empty) is
        # handled specially here.
        if not self.registry and not parsed_name.get_repo():
            name = "library/" + parsed_name.name
        else:
            name = parsed_name.name

        # Define tag for building the manifest's URL.
        tag = parsed_name.tag or "latest"

        # Try accessing manifest through HTTPS first.
        reg = get_registry_url(self.registry or DEFAULT_REGISTRY, "https")
        url = urljoin(reg, f"v2/{name}/manifests/{tag}")
        log.debug(f"Getting manifest from '{url}'.")
        res = self._do_get(url, name, headers)

        if res is not None and res.status_code == requests.codes["unauthorized"]:
            log.warning(f"Access to manifest for image '{image_name}' was not authorized;"
                        " be sure to pass a proper username/password pair for the registry.")

        elif res is None or res.status_code != requests.codes["ok"]:
            # Fall back to HTTP.
            log.debug("Attempt to access manifest via HTTPS failed with code "
                      f"{res.status_code if res else 'unknown'} - falling back to HTTP.")
            reg = get_registry_url(self.registry or DEFAULT_REGISTRY, "http")
            url = urljoin(reg, f"v2/{name}/manifests/{tag}")
            log.debug(f"Getting manifest from {url}")
            res = self._do_get(url, name, headers)

        if res is None or res.status_code != requests.codes["ok"]:
            raise InvalidDataError(f"Error: Could not determine digest for image '{image_name}'.")

        media_types = [MANIFEST_MEDIA_TYPE, MANIFEST_LIST_MEDIA_TYPE]
        if res.headers["content-type"] not in media_types:
            assert False, \
                f"Unexpected content-type for manifest of '{image_name}'"

        response_json = res.json()
        assert response_json["mediaType"] in media_types, \
                f"Wrong mediaType on manifest ({response_json['mediaType']})"
        assert response_json["schemaVersion"] == 2, \
                f"Wrong schemaVersion on manifest ({response_json['schemaVersion']})"

        if val_digest or ret_digest:
            digest_ = hashlib.sha256()
            digest_.update(res.content)
            digest = SHA256_PREFIX + digest_.hexdigest()
            log.debug(f"Manifest of '{name}', '{tag}' has digest '{digest}'")
            if tag.startswith(SHA256_PREFIX) and val_digest:
                # If the manifest was fetched by digest, make sure the returned
                # manifest's digest is the expected one.
                assert tag == digest, \
                    f"Manifest for {name}@{tag} has wrong digest ({digest})"
            if ret_digest:
                return res, digest

        return res

    def get_all_manifests(self, image_name,
                          headers=None, platforms=None, val_digest=True):
        """Iterate over all manifests of the given image

        :param image_name: Name of the image such as ubuntu:latest or fedora/httpd:latest;
                           the name should not contain a registry name (the registry is
                           specified to the constructor of the class).
        :param headers: Dict with extra headers to send to the server.
        :param platforms: If not None, an iterable indicating for which platforms to
                          fetch the manifests (by default).
        :param val_digest: Whether or not to validate the digest of the manifest (only
                           relevant when the image name also specifies a digest, e.g.
                           "ubuntu@sha256:123123..."
        :return: Iterator evaluating to (info, response) on each iteration,
                 where:
                 - info is a dictionary with fields "name", "type" ("manifest" or
                   "manifest-list"), "digest" (with the prefix "sha256:"), "platform"
                   (slash separated string) and "size";
                 - response is an HTTPResponse object.
        """

        top_parsed = parse_image_name(image_name)

        def _mkinfo(mtype, /, digest=None, platform=None, size=None):
            # Here we use the fact that the top-level and the child images have
            # the same name; just the digests are different.
            return {
                "name": top_parsed.name, "type": mtype, "digest": digest,
                "platform": platform, "size": size
            }

        # Handle top-level manifest which can be a simple manifest or a manifest list.
        top_res, top_digest = self.get_manifest(
            top_parsed.get_name_with_tag(),
            headers=headers, ret_digest=True, val_digest=val_digest)
        assert top_res.status_code == requests.codes["ok"], \
            f"Could not fetch manifest of '{image_name}'"
        if top_res.headers["content-type"] == MANIFEST_LIST_MEDIA_TYPE:
            yield _mkinfo("manifest-list", digest=top_digest), top_res
        elif top_res.headers["content-type"] == MANIFEST_MEDIA_TYPE:
            yield _mkinfo("manifest", digest=top_digest), top_res
        else:
            assert False, \
                f"Unexpected content-type for manifest of '{image_name}'"

        # Handle "child" manifests:
        if top_res.headers["content-type"] == MANIFEST_LIST_MEDIA_TYPE:
            top_data = top_res.json()
            assert top_data["mediaType"] == MANIFEST_LIST_MEDIA_TYPE, \
                f"Wrong mediaType of top-level manifest ({top_data['mediaType']})"
            assert top_data["schemaVersion"] == 2, \
                f"Wrong schemaVersion of top-level manifest ({top_data['schemaVersion']})"
            for child in top_data["manifests"]:
                child_platform = platform_str(child["platform"])
                if platforms is not None and not platform_in(child_platform, platforms):
                    log.debug(f"Skipping manifest for platform {child_platform}")
                    continue
                child_parsed = deepcopy(top_parsed)
                child_parsed.set_tag(child["digest"])
                child_res = self.get_manifest(
                    child_parsed.get_name_with_tag(),
                    headers=headers, ret_digest=False, val_digest=val_digest)
                assert child_res.headers["content-type"] == MANIFEST_MEDIA_TYPE, \
                    (f"Child manifests of type {child_res.headers['content-type']}"
                     "are not supported.")
                child_info = _mkinfo(
                    "manifest",
                    digest=child["digest"], platform=child_platform,
                    size=child["size"])
                yield child_info, child_res

    def save_all_manifests(self, image_name, dest_dir,
                           headers=None, platforms=None, val_digest=True):
        """Save the manifests of the image specified (in JSON format)

        :param image_name: Name of the image such as ubuntu:latest or fedora/httpd:latest;
                           the name should not contain a registry name (the registry is
                           specified to the constructor of the class).
        :param dest_dir: Destination directory of the manifests.
        :param headers: Dict with extra headers to send to the server.
        :param platforms: If not None, an iterable indicating for which platforms to
                          fetch the manifests (by default).
        :param val_digest: Whether or not to validate the digest of the manifest (only
                           relevant when the image name also specifies a digest, e.g.
                           "ubuntu@sha256:123123..."
        :param cached: Iterable with the digests already fetched (TODO).
        """
        manifests_info = []
        saved_digests = []
        kwargs = {
            "headers": headers,
            "platforms": platforms,
            "val_digest": val_digest
        }
        # TODO: Pass `cached` to get_all_manifests().
        for info, resp in self.get_all_manifests(image_name, **kwargs):
            # Determine destination.
            _fname = info["digest"]
            assert _fname.startswith(SHA256_PREFIX)
            _fname = _fname[len(SHA256_PREFIX):]
            _dest = os.path.join(dest_dir, _fname + ".json")

            # Save some information about the image.
            manifests_info.append({
                "type": info["type"],
                "name": info["name"],
                "digest": info["digest"],
                "platform": info["platform"],
                "manifest-file": _dest
            })

            # Save file:
            log.info(f"Saving {info['type']} of {info['name']} [{info['platform']}]")
            # log.info(f"Saving {info['type']} of {info['name']} [{info['platform']}]\n"
            # f"  into {_dest}")
            with open(_dest, "wb") as fileh:
                fileh.write(resp.content)
            saved_digests.append(info["digest"])

        return saved_digests, manifests_info


def platform_str(platform):
    """Transform a platform object into its string form."""
    _platform = None
    if platform:
        _platform = f"{platform['os']}/{platform['architecture']}"
        if "variant" in platform:
            _platform += f"/{platform['variant']}"
        if "os.version" in platform:
            _platform += f"/{platform['os.version']}"
    return _platform


def platform_matches(plat1, plat2, ret_grade=False):
    """Determine if two platform specification strings match.

    E.g. linux matches linux/
         linux matches linux/arm
         linux matches linux/arm/v5
         linux/arm matches linux/arm/v7
         linux/arm/v5 DOES NOT match linux/arm/v6
         linux DOES NOT match windows
    """
    # TODO: Determine if there are defined rules for how to compare platforms.
    #       e.g. can we say that linux/arm/v7 encompasses linux/arm/v6?
    if plat1[-1] == '/':
        plat1 = plat1[:-1]
    if plat2[-1] == '/':
        plat2 = plat2[:-1]
    plat1_lst = plat1.split("/")
    plat2_lst = plat2.split("/")

    match, grade = True, 0
    for el1, el2 in zip(plat1_lst, plat2_lst):
        if el1 != el2:
            match = False
            break
        grade += 1

    if ret_grade:
        return match, grade

    return match


def platform_in(plat, plat_list):
    """Determine if a platform string belongs to a list.

    :return: True iff a given platform string matches (as per platform_matches())
             any of the ones in a given list
    """
    return any(platform_matches(_plat, plat) for _plat in plat_list)


# EOF
