"""One Waitress process per container; proxy trust is restricted to an explicit IP."""
from ipaddress import ip_address
import os

from waitress import serve


def server_options():
    options = {'host': '0.0.0.0', 'port': 5000, 'threads': 4, 'expose_tracebacks': False,
               'clear_untrusted_proxy_headers': True}
    proxy = os.environ.get('COURSESPHERE_TRUSTED_PROXY', '')
    if proxy:
        try:
            ip_address(proxy)
        except ValueError:
            raise ValueError('COURSESPHERE_TRUSTED_PROXY must be one explicit proxy IP.') from None
        options.update(trusted_proxy=proxy, trusted_proxy_count=1,
                       trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto'})
    return options


def main():
    options = server_options()
    from endpoints import app
    from structured_logging import log_event
    log_event(app, 'application_started', mode='local mode' if os.environ.get('COURSESPHERE_LOCAL') == '1' else 'firebase')
    serve(app, **options)


if __name__ == '__main__':
    main()
