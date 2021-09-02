"""Helper functions and classes for working with Docker registries."""

import hashlib
import logging
import os
import re
from urllib.parse import urljoin

import requests
from tcbuilder.errors import TorizonCoreBuilderError

log = logging.getLogger("torizon." + __name__)

# As per https://docs.docker.com/engine/reference/commandline/tag/,
# default registry is "registry-1.docker.io".
# TODO: Determine why docker info shows "https://index.docker.io/"
DEFAULT_REGISTRY = "https://registry-1.docker.io/"

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

    :param header: Value of the WWW-Authenticate header to parse in the form
                   `Bearer attr1=value1,attr2=value2,...
    :return: (scheme, attributes) where scheme is always "Bearer" and attributes
             is a list of pairs (attr, value).
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

    def get_name_with_tag(self):
        """Get name of the image including the tag or digest"""
        _tag = self.tag or "latest"
        if _tag.startswith(SHA256_PREFIX):
            return f"{self.name}@{_tag}"
        return f"{self.name}:{_tag}"

    def __repr__(self):
        return (f"ImageName(registry='{self.registry}', "
                f"name='{self.name}', tag='{self.tag}')")


def parse_image_name(image_name):
    """Parse an image name as per Docker image tagging specification

    As per https://docs.docker.com/engine/reference/commandline/tag/, an
    image name is made up of slash-separated name components, optionally
    prefixed by a registry hostname.

    parse_image_name('ubuntu:latest')
    => ParsedImageName(registry=None, name='ubuntu', tag='latest')
    parse_image_name('linux/ubuntu:latest')
    => ParsedImageName(registry=None, name='linux/ubuntu', tag='latest')
    parse_image_name('localhost:8000/ubuntu:latest')
    => ParsedImageName(registry='localhost:8000', name='ubuntu', tag='latest')
    parse_image_name('http://localhost/ubuntu:latest')
    => ParsedImageName(registry='http://localhost/', name='ubuntu', tag='latest')
    parse_image_name('http://localhost:8000/ubuntu:latest')
    => ParsedImageName(registry='http://localhost:8000/', name='ubuntu', tag='latest')
    parse_image_name('http://localhost/linux/ubuntu:latest')
    => ParsedImageName(registry='http://localhost/', name='linux/ubuntu', tag='latest')
    parse_image_name('http://localhost/linux/ubuntu@sha256:1234')
    => ParsedImageName(registry='http://localhost/', name='linux/ubuntu', tag='sha256:1234')
    """

    try:
        known_schemes = ["http://", "https://"]
        registry = None
        name_with_tag = image_name
        # Get scheme and registry name if possible.
        for _scheme in known_schemes:
            if name_with_tag.lower().startswith(_scheme):
                registry = name_with_tag[:len(_scheme)]
                name_with_tag = name_with_tag[len(_scheme):]
                registry_, name_with_tag = name_with_tag.split("/", 1)
                registry += registry_ + "/"

        # Parse the rest (repo/name):
        comps = name_with_tag.split("/")
        if registry is None and len(comps) == 2:
            # E.g. fedora/httpd:latest, localhost:8000/httpd:latest
            if ":" in comps[0]:
                registry, name_with_tag = comps
        elif registry is None and len(comps) == 3:
            # E.g. gcr.io/fedora/httpd:latest
            registry, name_with_tag = name_with_tag.split("/", 1)

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

    except ValueError as _exc:
        raise TorizonCoreBuilderError(
            f"Cannot parse image name {image_name}")


class RegistryOperations:
    """Class providing operations on a Docker registry"""

    LOGINS = []

    @classmethod
    def set_logins(cls, logins):
        """Set the username/password for authenticating with registries

        :param logins: A list-like object where one element is a pair (username, password)
                       to be used with the default registry and the other items are 3-tuples
                       (registry, username, password) with authentication information to
                       be used with other registries.
        """
        cls.LOGINS = logins.copy()

    def __init__(self, regurl=None):
        # Ensure registry URL ends with a slash.
        if regurl and regurl[-1] == "/":
            regurl += "/"
        self.regurl = regurl or DEFAULT_REGISTRY
        self.token_cache = {}
        # TODO: Ensure regurl specifies a scheme.

    # pylint:disable=no-self-use
    def _parse_www_auth_header(self, headers):
        """Parse the WWW-Authenticate header extracting realm, service, scopes"""

        scheme, attribs = parse_www_auth_header(headers["www-authenticate"])
        # --
        # Expected format (https://docs.docker.com/registry/spec/auth/token/):
        # Bearer realm="https://auth.docker.io/token",
        #        service="registry.docker.io",
        #        scope="repository:samalba/my-app:pull,push"
        # With scope being a space-separated list of scopes.
        # --
        assert scheme == 'Bearer', \
            f"Only supported authorization scheme is 'Bearer' != '{scheme}'"
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
        return realm, service, scopes
    # pylint:enable=no-self-use

    def _request_token(self, headers):
        """Get the OAuth2 token required for accessing some resources"""

        realm, service, scopes = self._parse_www_auth_header(headers)
        auth_url = urljoin(self.regurl, realm)
        auth_parms = []
        auth_parms.append(("service", service))
        for scope in scopes:
            auth_parms.append(("scope", scope))

        if self.regurl == DEFAULT_REGISTRY:
            # Handler username/password authentication with default registry.
            logins = [login for login in self.LOGINS if len(login) == 2]
            assert len(logins) < 2, "Multiple logins for the same registry!"
            if logins:
                _auth = tuple(logins[0])
                res = requests.get(auth_url, params=auth_parms, auth=_auth)
            else:
                res = requests.get(auth_url, params=auth_parms)
        else:
            # TODO: Handle non-default registry.
            assert False

        res_json = res.json()
        for scope in scopes:
            self.token_cache[scope] = res_json["token"]

    def get_manifest(self, image_name, headers=None, ret_digest=False, val_digest=True):
        """Get the manifest of the specified image

        :param image_name: Name of the image such as ubuntu:latest or fedora/httpd:latest;
                           the name should not contain a registry name (the registry is
                           specified to the constructor of the class).
        :param headers: Dict with extra headers to send to the server.
        :param ret_digest: Whether or not to return the digest of the manifest as part
                           of the function's output.
        :param val_digest: Whether or not to validate the digest of the manifest (only
                           relevant when the image name also specifies a digest, e.g.
                           "ubuntu@sha256:123123..."
        :return: (response, digest) if ret_digest=True or only the response otherwise.
        """

        headers = headers or {}
        headers = headers.copy()
        headers.update(DEFAULT_GET_MANIFEST_HEADERS)

        parsed_name = parse_image_name(image_name)
        assert not parsed_name.registry, \
            "Registry name cannot be passed to get_manifest()"
        # Define name for building the manifest's URL.
        if not parsed_name.get_repo():
            name = "library/" + parsed_name.name
        else:
            name = parsed_name.name

        # Define tag for building the manifest's URL.
        tag = parsed_name.tag or "latest"

        # Get absolute URL.
        url = urljoin(self.regurl, f"v2/{name}/manifests/{tag}")

        # Helper to do the request setting the headers.
        def _do_request():
            nonlocal headers
            _scope = f"repository:{name}:pull"
            if _scope in self.token_cache:
                log.debug(f"Using cached token for scope {_scope}")
                _token = self.token_cache[_scope]
                # Add header:
                headers.update({
                    "Authorization": f"Bearer {self.token_cache[_scope]}"
                })
            else:
                log.debug(f"No token cached for scope {_scope}")
            res = requests.get(url, headers=headers)
            # log.debug(f"Response: {res.text}")
            return res

        # Perform request.
        res = _do_request()
        # Perform request with an access token (if needed).
        if res.status_code == requests.codes["unauthorized"]:
            self._request_token(headers=res.headers)
            res = _do_request()

        if res.status_code != requests.codes["ok"]:
            return (res, None) if ret_digest else res

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

        _parsed = parse_image_name(image_name)
        name = _parsed.name

        def _mkinfo(mtype, /, digest=None, platform=None, size=None):
            nonlocal name
            return {
                "name": name, "type": mtype, "digest": digest,
                "platform": platform, "size": size
            }

        # Handle top-level manifest which can be a simple manifest or a manifest list.
        top_res, top_digest = self.get_manifest(
            image_name, headers=headers, ret_digest=True, val_digest=val_digest)
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
                "Wrong mediaType of top-level manifest ({top_data['mediaType']})"
            assert top_data["schemaVersion"] == 2, \
                "Wrong schemaVersion of top-level manifest ({top_data['schemaVersion']})"
            for child in top_data["manifests"]:
                child_platform = platform_str(child["platform"])
                if platforms is not None and not platform_in(child_platform, platforms):
                    log.debug(f"Skipping manifest for platform {child_platform}")
                    continue
                child_res = self.get_manifest(
                    f"{name}@{child['digest']}",
                    headers=headers, ret_digest=False, val_digest=val_digest)
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
