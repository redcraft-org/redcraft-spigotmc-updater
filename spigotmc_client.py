import os
import base64
import io

import cloudscraper
import requests
from tqdm import tqdm
from bs4 import BeautifulSoup

from utils.plugin_info import extract_plugin_info


class SpigotMcClient:

    base_url = 'https://www.spigotmc.org'

    # Needs to be a well known plugin with an external download
    plugin_to_escalate_token = 'https://www.spigotmc.org/resources/fast-async-worldedit-voxelsniper.13932/download?version=320370'

    cloudproxy_url = 'http://localhost:8191/v1'

    session = None
    logout_url = None

    def log_in(self, login, password, cloudproxy_url=None):
        if cloudproxy_url:
            self.cloudproxy_url = cloudproxy_url

        self.session = cloudscraper.create_scraper()
        self.session.get('{}/login'.format(self.base_url))

        data = {
            'login': login,
            'password': password,
            'register': '0',
            'remember': '0'
        }

        login_response = self.session.post('{}/login/login'.format(self.base_url), data=data)
        login_parser = BeautifulSoup(login_response.text, features='html.parser')

        logout_link = login_parser.find('a', {'class': 'LogOut'})

        if logout_link is None:
            raise ValueError('Couldn\'t get a logout link, login probably failed.')

        self.logout_url = logout_link.get('href')

        self.escalate_token()

    def get_cloudproxy_session(self):
        self.clear_cloudproxy_sessions()

        session_create_request = {
            'cmd': 'sessions.create'
        }
        session_create_response = requests.post(self.cloudproxy_url, json=session_create_request)

        return session_create_response.json().get('session')

    def clear_cloudproxy_sessions(self):
        session_list_request = {
            'cmd': 'sessions.list'
        }
        session_list_response = requests.post(self.cloudproxy_url, json=session_list_request)

        for session_id in session_list_response.json().get('sessions'):
            session_destroy_request = {
                'cmd': 'sessions.destroy',
                'session': session_id
            }
            requests.post(self.cloudproxy_url, json=session_destroy_request)


    def escalate_token(self):
        cloudproxy_session_id = self.get_cloudproxy_session()

        cookies = []
        for cookie in self.session.cookies:
            cookies.append({
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain
            })

        user_agent = self.session.headers['User-Agent']

        elevation_data = {
            'cmd': 'request.get',
            'url': self.plugin_to_escalate_token,
            'userAgent': user_agent,
            'cookies': cookies,
            'session': cloudproxy_session_id
        }

        print('Escalating token, this may take a while...')

        escalate_elevation_response = self.session.post(self.cloudproxy_url, json=elevation_data)
        escalate_elevation_code = escalate_elevation_response.status_code

        if escalate_elevation_code >= 500:
            raise ValueError('Escalate token first step failed, got status code {}'.format(escalate_elevation_code))

        base_cookies_data = {
            'cmd': 'request.get',
            'url': self.base_url,
            'userAgent': user_agent,
            'session': cloudproxy_session_id
        }

        escalate_base_cookies_response = self.session.post(self.cloudproxy_url, json=base_cookies_data)
        escalate_base_cookies_code = escalate_base_cookies_response.status_code

        self.clear_cloudproxy_sessions()

        if escalate_base_cookies_code >= 500:
            raise ValueError('Escalate token second step failed, got status code {}'.format(escalate_base_cookies_code))

        escalated_cookies = escalate_base_cookies_response.json().get('solution', {}).get('cookies', [])

        self.session.cookies.clear()
        for cookie in escalated_cookies:
            cookie_obj = requests.cookies.create_cookie(cookie['name'], cookie['value'], domain=cookie['domain'])
            self.session.cookies.set_cookie(cookie_obj)

        print('Token escalated!')

    def get_watched_plugins(self):
        plugins = {}

        first_watched_resources_response = self.session.get('{}/resources/watched'.format(self.base_url))
        first_watched_resources_parser = BeautifulSoup(first_watched_resources_response.text, features='html.parser')

        page_selector_element = first_watched_resources_parser.find('div', {'class': 'PageNav'})
        last_page = int(page_selector_element.get('data-last') or 0) + 1

        for page_number in tqdm(range(1, last_page), desc='Exploring watched plugins pages'):
            current_watched_resources_response = self.session.get('{}/resources/watched?page={}'.format(self.base_url, page_number))
            current_watched_resources_parser = BeautifulSoup(current_watched_resources_response.text, features='html.parser')

            resources = current_watched_resources_parser.findAll('li', {'class': 'resourceListItem'})
            for resource in resources:
                plugin_url_element = resource.find('h3').find('a')
                plugin_url = '{}/{}'.format(self.base_url, plugin_url_element.get('href'))
                plugin_name = plugin_url_element.text
                plugin_version = resource.find('span', {'class': 'version'}).text
                plugin_id = resource.find('input', {'name': 'resource_ids[]'}).get('value')

                plugins[plugin_id] = {
                    'id': plugin_id,
                    'url': plugin_url,
                    'display_name': plugin_name,
                    'version': plugin_version
                }

        return plugins

    def download_plugin(self, plugin, output_folder):
        plugin_page_response = self.session.get(plugin['url'])
        plugin_page_parser = BeautifulSoup(plugin_page_response.text, features='html.parser')

        download_button = plugin_page_parser.find('label', {'class': 'downloadButton'})
        size_or_external = download_button.find('small', {'class': 'minorText'}).text

        if size_or_external == 'Via external site':
            plugin['name'] = plugin['display_name']
            return plugin

        relative_download_link = download_button.find('a').get('href')
        plugin_download_link = '{}/{}'.format(self.base_url, relative_download_link)

        plugin_binary_response = self.session.get(plugin_download_link)
        plugin_data = plugin_binary_response.content

        zip_handle = io.BytesIO(plugin_data)

        file_name = None

        try:
            plugin_metadata = extract_plugin_info(zip_handle)
            file_name = '{name}.jar'.format(**plugin_metadata)
            plugin.update(plugin_metadata)
        except Exception:
            # Means it's not a plugin but a zip file
            plugin['name'] = plugin['display_name']
            file_name = '{name}.zip'.format(**plugin)

        file_path = os.path.join(output_folder, file_name)

        with open(file_path, 'wb') as file:
            file.write(plugin_data)

        plugin['name'] = plugin['display_name']

        return plugin