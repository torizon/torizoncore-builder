import io
import re

class CompatibleOverlayParser:
    def __init__(self, sourcefile):
        with io.open(sourcefile, "r") as f:
            self.file_content = f.read()
        self.counter = 0
        self.description = ""

    def extract_comments(self):
        comments = re.sub(r'// *([^\n]*\n)|/\*(.*)\*/|[^\n]*\n', r'\1\2',
                          self.file_content, flags=re.DOTALL)

        return comments

    def get_description(self):
        # By convention, the first (non-SPDX) comment contains a description
        # of the overlay.
        comments = self.extract_comments()
        # Remove SPDX License Identifier
        comments = re.sub(r'SPDX-License-Identifier: ([^\n]*)\n', '', comments,
                          flags=re.DOTALL)
        self.description = comments.split("\n")[0]
        return self.description

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
        compatibility_list = ""

        # Search for the main part \{ ... };
        main_content = re.sub(r'.*/ {(.*)} *;', r'\1', self.file_content, flags=re.DOTALL)
        # Remove all innter nodes we only want the root properties
        outer_block = re.sub(r'.*?[{;]', self.block_repl, main_content, flags=re.DOTALL)
        # Get the compatibility props
        compatible = re.sub(r'.*?compatible *= *(.*?);', r'\1,', outer_block, flags=re.DOTALL)
        compatible = re.sub(r'[\n\r]', '', compatible)

        #compatible_list = re.split(r'" *, *"?', compatible)
        compatibility_list = re.findall(r'.*?"(.*?)" *, *', compatible)

        return compatibility_list

    @staticmethod
    def check_compatibility(compatibilities, overlay_compatibilities):
        for compatibility in compatibilities:
            # Check if we have a matching compatibility in the overlay...
            if compatibility in overlay_compatibilities:
                return True

        return False
