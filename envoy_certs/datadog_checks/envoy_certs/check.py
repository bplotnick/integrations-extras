from typing import Any

import requests

from datadog_checks.base import AgentCheck

# content of the special variable __version__ will be shown in the Agent status page
__version__ = "1.0.0"


class EnvoyCertsCheck(AgentCheck):
    SERVICE_CHECK_NAME = 'envoy_certs.can_connect'
    TTL_METRIC_NAME = 'envoy_certs.days_until_expiration'

    def check(self, _):
        # type: (Any) -> None

        # the next few blocks are taken directly from the Envoy integration
        custom_tags = self.instance.get('tags', [])

        try:
            certs_url = self.instance['certs_url']
        except KeyError:
            msg = 'Envoy configuration setting `certs_url` is required'
            self.service_check(self.SERVICE_CHECK_NAME, AgentCheck.CRITICAL, message=msg, tags=custom_tags)
            self.log.error(msg)
            return

        try:
            response = self.http.get(certs_url)
        except requests.exceptions.Timeout:
            timeout = self.http.options['timeout']
            msg = 'Envoy endpoint `{}` timed out after {} seconds'.format(certs_url, timeout)
            self.service_check(self.SERVICE_CHECK_NAME, AgentCheck.CRITICAL, message=msg, tags=custom_tags)
            self.log.exception(msg)
            return
        except (requests.exceptions.RequestException, requests.exceptions.ConnectionError):
            msg = 'Error accessing Envoy endpoint `{}`'.format(certs_url)
            self.service_check(self.SERVICE_CHECK_NAME, AgentCheck.CRITICAL, message=msg, tags=custom_tags)
            self.log.exception(msg)
            return

        if response.status_code != 200:
            msg = 'Envoy endpoint `{}` responded with HTTP status code {}'.format(certs_url, response.status_code)
            self.service_check(self.SERVICE_CHECK_NAME, AgentCheck.CRITICAL, message=msg, tags=custom_tags)
            self.log.warning(msg)
            return

        certs = {}
        # Re-key by serial number to dedupe the certs
        for c in response.json()['certificates']:
            for cert in c['ca_cert']:
                certs[cert['serial_number']] = cert

            for cert in c['cert_chain']:
                certs[cert['serial_number']] = cert

        for cert in certs.values():
            # FIXME(plotnick): Until we can get a real name, we have to try to come up
            # with a name ourselves using some heuristics
            self._cert_check(cert, custom_tags)

        self.service_check(self.SERVICE_CHECK_NAME, AgentCheck.OK, tags=custom_tags)

    def _cert_check(self, cert, custom_tags):
        """ Runs a check over a single cert """
        name = None
        tags = []  # This should have the same cardinality as name
        # "inline" means that the cert came from SDS
        if "inline" not in cert['path']:
            name = cert['path']
            tags.append("path:{}".format(cert['path']))

        subject_alt_names = cert.get("subject_alt_names")
        # Note: If there are multiple SANs, we take the first one
        if subject_alt_names:
            # We aren't recording whether it's a DNS SAN or URL SAN. It doesn't matter for this
            san = list(subject_alt_names[0].values())[0]
            if not name:
                name = san
            tags.append("san:{}".format(san))

        # It's possible to have no name at this point. But it's still fine to have name:None
        tags.append("name:{}".format(name))
        tags.extend(custom_tags)
        self.gauge(self.TTL_METRIC_NAME, value=cert['days_until_expiration'], tags=tags)
        return
