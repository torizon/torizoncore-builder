import logging

from tcbuilder.backend.ostree import OSTreeKey
from tcbuilder.errors import InvalidArgumentError

log = logging.getLogger("torizon." + __name__)


def parse_ostree_key(ostree_key, *, ostree_key_dir=None):
    """
    Parse an OSTree key from a formatted string and return an OSTreeKey object.

    The expected format of the OSTree key is "name=<NAME>;algo=<ALGO>".
    This function extracts the key name and algorithm from the provided string.
    If the algorithm is not specified, a default value is used.

    :param ostree_key: A string representing the OSTree key, formatted as
        "name=<NAME>;algo=<ALGO>".
    :param ostree_key_dir: An optional directory where the key is located.
    :returns: An instance of the OSTreeKey class containing the parsed key
          information.
    :raises InvalidArgumentError: If the format of the `ostree_key` is
          incorrect, or if the key name is not specified.
    """

    key_name = ""
    key_algo = ""
    for element in ostree_key.split(';'):
        argpair = element.split('=')
        if len(argpair) != 2:
            raise InvalidArgumentError(
                "The ostree-key parameter is not correctly formatted. "
                "Did you separate each field with a semicolon (;) ?")
        argkey, argvalue = argpair
        argkey = argkey.strip()
        if argkey == "name":
            key_name = argvalue.strip()
        elif argkey == "algo":
            key_algo = argvalue.strip()
        else:
            log.warning("Unknown key '%s' in ostree-key parameter was ignored.", argkey)

    if not key_name:
        raise InvalidArgumentError(
            "The key name was not specified via the ostree-key parameter. Aborting.")

    if not key_algo:
        log.info("Could not find value of 'algo' in the ostree-key parameter. "
                 f"Defaulting to '{OSTreeKey.OSTREE_KEY_DEFAULT_ALGO}'.")
        key_algo = OSTreeKey.OSTREE_KEY_DEFAULT_ALGO

    # Wrap key information into appropriate object:
    key_obj = OSTreeKey(key_dir=ostree_key_dir, key_name=key_name, key_algo=key_algo)

    return key_obj
