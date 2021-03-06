import io
import re
from zipfile import ZipFile


class ZipPostProcessor:
    def process(
        self, downloaded_binary, source, name, url, archive_filter=None, **kwargs
    ):
        # Decompress .zip archive and return the content of the matched regex
        filter_regex = re.compile(archive_filter.replace("*", ".+"))
        file_handler = io.BytesIO(downloaded_binary)

        with ZipFile(file_handler, "r") as file_contents:
            for file in file_contents.namelist():
                if not filter_regex or filter_regex.match(file):
                    with file_contents.open(file, "r") as target_file:
                        downloaded_binary = target_file.read()
                        break

        return downloaded_binary, source, name, url
