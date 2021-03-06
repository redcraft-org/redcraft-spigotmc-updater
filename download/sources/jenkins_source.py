import requests

from download.sources.direct_source import DirectSource


class JenkinsSource(DirectSource):

    session = None

    def __init__(self):
        self.session = requests.session()

    def download_element(self, url, filter=None, **_):
        filter_regex = self.get_filter_regex(filter)

        stripped_url = url.strip("/")

        # Get the last successful build
        jenkins_json_url = "{}/lastSuccessfulBuild/api/json".format(stripped_url)

        jenkins_response = self.session.get(jenkins_json_url).json()

        for artifact in jenkins_response.get("artifacts") or []:
            # Find and return the file from the build
            if filter_regex.match(artifact["fileName"]):
                artifact_url = "{}/lastSuccessfulBuild/artifact/{}".format(
                    stripped_url, artifact["relativePath"]
                )

                return self.session.get(artifact_url).content

        raise ValueError(
            'Could not find a matching a matching artifact "{}" at {}'.format(
                filter, jenkins_json_url
            )
        )
