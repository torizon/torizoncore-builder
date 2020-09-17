import io
import re
import subprocess

class CompatibleOverlayParser:
    def __init__(self):
        self.counter = 0
        self.description = ""

    def extract_comments(self, sourcefile):
        with io.open(sourcefile, "r") as f:
            file_content = f.read()
            comments = re.sub(r'// *([^\n]*\n)|/\*(.*)\*/|[^\n]*\n', r'\1\2',
                              file_content, flags=re.DOTALL)

        return comments

    def parse(self, sourcefile):
        comments = self.extract_comments(sourcefile)
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

    def get_compatibilities_binary(self, file=None):
        compatibility_list = ""
        fdtget_cmd = f"fdtget {file} / compatible"
        std_output = subprocess.check_output(fdtget_cmd, shell=True)
        compatibility_list = std_output.decode('utf-8').strip().split()
        return compatibility_list

    def get_compatibilities_source(self, file=None):
        compatibility_list = ""
        with io.open(file, "r") as f:
            dts_content = f.read()

        # Search for the main part \{ ... };
        main_content = re.sub(r'.*/ {(.*)} *;', r'\1', dts_content, flags=re.DOTALL)
        # Remove all innter nodes we only want the root properties
        outer_block = re.sub(r'.*?[{;]', self.block_repl, main_content, flags=re.DOTALL)
        # Get the compatibility props
        compatible = re.sub(r'.*?compatible *= *(.*?);', r'\1,', outer_block, flags=re.DOTALL)
        compatible = re.sub(r'[\n\r]', '', compatible)

        #compatible_list = re.split(r'" *, *"?', compatible)
        compatibility_list = re.findall(r'.*?"(.*?)" *, *', compatible)

        return compatibility_list

    def check_compatibility(self, compatibilities, overlay):
        overlay_compatibilities = self.get_compatibilities_source(overlay)

        for compatibility in compatibilities:
            for overlay_compatibility in overlay_compatibilities:
                # If there is a match
                if overlay_compatibility == compatibility:
                    return True

        return False
