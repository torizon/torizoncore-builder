import io
import re

# Regex for comments
comments_re = re.compile(r"(?:\/\*((?:.|\n)*?)\*\/)|\/\/(.*$)", re.MULTILINE | re.ASCII)
comment_spdx_re = re.compile(r'SPDX-License-Identifier: ([^\n]*)\n', re.DOTALL)

# Regex for compatible parsing
content_re = re.compile(r".*\/\s{(.*)}\s*;", re.MULTILINE | re.ASCII | re.DOTALL)
find_block_re = re.compile(r'.*?[{;]', re.DOTALL)
compatible_re = re.compile(r".*?compatible\s*=\s*(.*?);", re.DOTALL)
strings_re = re.compile(r'"([^"]*)"')

class CompatibleOverlayParser:
    def __init__(self, sourcefile):
        with io.open(sourcefile, "r") as srcf:
            self.file_content = srcf.read()
        self.counter = 0
        self.description = ""

    def extract_comments(self):
        groups = comments_re.findall(self.file_content)
        comments = []
        for group in groups:
            for match in group:
                comment = match.strip()
                if len(comment) > 0:
                    comments.append(comment)
        return comments

    def get_description(self):
        # By convention, the first (non-SPDX) comment contains a description
        # of the overlay.
        comments = self.extract_comments()

        # Return first non-SPDX header comment
        for comment in comments:
            if not comment_spdx_re.match(comment):
                return comment

        return None

    def block_repl(self, matchobj):
        text = matchobj.group(0)
        if "{" in text:
            self.counter += 1

        if self.counter > 0:
            ret = None
        else:
            ret = text

        if "}" in text:
            self.counter -= 1

        return ret

    def get_compatibilities_source(self):
        """Get list of compatibilities, returns None if not found"""
        # Search for the main part \{ ... };
        match = content_re.match(self.file_content)
        if not match:
            return None

        main_content = match.group(1)

        # Remove all inner nodes we only want the root properties
        outer_block = find_block_re.sub(self.block_repl, main_content)

        # Get the compatibility props
        match = compatible_re.match(outer_block)
        if not match:
            return None

        compatible_value = match.group(1)

        compatibility_list = strings_re.findall(compatible_value)

        return compatibility_list

    @staticmethod
    def check_compatibility(compatibilities, overlay_compatibilities):
        if compatibilities is None:
            return False

        for compatibility in compatibilities:
            # Check if we have a matching compatibility in the overlay...
            if compatibility in overlay_compatibilities:
                return True

        return False
