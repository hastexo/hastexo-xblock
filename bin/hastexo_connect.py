#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fetches SSH key from Swift, if necessary, and opens and interactive SSH
session using it.

Based on GateOne's ssh_connect.py.

Authors:

Dan McDougall <daniel.mcdougall@liftoffsoftware.com>
Adolfo R. Brandes <adolfo.brandes@hastexo.com>

"""
from __future__ import unicode_literals

import os, sys, readline, signal
import tempfile, io
import traceback
import logging
import socket
import errno
import json
import re

from optparse import OptionParser, OptionError
from hastexo.swift import SwiftWrapper
from hastexo.utils import SETTINGS_KEY, DEFAULT_SETTINGS, get_xblock_configuration
from concurrent import futures

# Python 3 compatibility
if bytes != str:
    raw_input = input

# Disable ESC autocomplete for local paths (prevents information disclosure)
readline.parse_and_bind('esc: none')

# Disable swiftclient logs
swiftclient_logger = logging.getLogger("swiftclient")
swiftclient_logger.propagate = False

wrapper_script = """\
#!/bin/sh
# This variable is for easy retrieval later
trap "rm -f {temp}" EXIT
{cmd}
echo '[Press Enter to close this terminal]'
read waitforuser
rm -f {temp} # Cleanup
exit 0
"""

def mkdir_p(path):
    """Pythonic version of mkdir -p"""
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            pass
        else: raise

def which(binary, path=None):
    """
    Returns the full path of *binary* (string) just like the 'which' command.
    Optionally, a *path* (colon-delimited string) may be given to use instead of
    os.environ['PATH'].

    """
    if path:
        paths = path.split(':')
    else:
        paths = os.environ['PATH'].split(':')

    for path in paths:
        if not os.path.exists(path):
            continue
        files = os.listdir(path)
        if binary in files:
            return os.path.join(path, binary)

    return None

def valid_hostname(hostname):
    """
    Returns True if the given *hostname* is valid according to RFC rules.  Works
    with Internationalized Domain Names (IDN) and hostnames with an
    underscore.
    """
    # Convert to Punycode if an IDN
    try:
        hostname = hostname.encode('idna')
    except UnicodeError: # Can't convert to Punycode: Bad hostname
        return False

    try:
        hostname = str(hostname, 'UTF-8')
    except TypeError: # Python 2.6+.  Just ignore
        pass

    if len(hostname) > 255:
        return False

    if hostname[-1:] == ".": # Strip the tailing dot if present
        hostname = hostname[:-1]

    allowed = re.compile("(?!-)[_A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)

    return all(allowed.match(x) for x in hostname.split("."))

def valid_ip(ipaddr):
    """
    Returns True if *ipaddr* is a valid IPv4 or IPv6 address.
    (from http://stackoverflow.com/questions/319279/how-to-validate-ip-address-in-python)
    """
    if ':' in ipaddr: # IPv6 address
        try:
            socket.inet_pton(socket.AF_INET6, ipaddr)
            return True
        except socket.error:
            return False
    else:
        try:
            socket.inet_pton(socket.AF_INET, ipaddr)
            return True
        except socket.error:
            return False

def download_identity(provider, identity, identity_path):
    # Load LMS env file
    lms_env_path = '/edx/app/edxapp/lms.env.json'
    with open(lms_env_path) as env_file:
        tokens = json.load(env_file)

    # Get configuration
    xblock_settings = tokens.get('XBLOCK_SETTINGS')
    if xblock_settings:
        settings = xblock_settings.get(SETTINGS_KEY, DEFAULT_SETTINGS)
    else:
        settings = DEFAULT_SETTINGS
    configuration = get_xblock_configuration(settings, provider)

    # Download it, if necessary
    if configuration.get('ssh_upload'):
        swift = SwiftWrapper(**configuration)
        swift.download_key(identity, identity_path)

def openssh_connect(user, host, provider, identity,
        port=22,
        config=None,
        env=None,
        additional_args=None,
        debug=False):
    """
    Starts an interactive SSH session to the given host as the given user on the
    given port, with the given identity.

    If *env* (dict) is given, that will be used for the shell env when opening
    the SSH connection.

    If *additional_args* is given this value (or values if it is a list) will be
    added to the arguments passed to the ssh command.

    If *debug* is ``True`` then '-vvv' will be passed to the ssh command.
    """
    try:
        int(port)
    except ValueError:
        print("The port must be an integer < 65535")
        sys.exit(1)

    # Unless we enable SendEnv in ssh these will do nothing
    if not env:
        env = {
            'TERM': 'xterm',
            'LANG': 'en_US.UTF-8',
        }

    try:
        env['LINES'] = os.environ['LINES']
        env['COLUMNS'] = os.environ['COLUMNS']
        env['GO_TERM'] = os.environ['GO_TERM']
        env['GO_LOCATION'] = os.environ['GO_LOCATION']
        env['GO_SESSION'] = os.environ['GO_SESSION']
    except KeyError:
        pass

    # Get the user's ssh directory
    if 'GO_USER' in os.environ: # Try to use Gate One's provided user first
        go_user = os.environ['GO_USER']
    else:
        # Fall back to the executing user (for testing outside of Gate One)
        go_user = os.environ['USER']

    if 'GO_USER_DIR' in os.environ:
        users_dir = os.path.join(os.environ['GO_USER_DIR'], go_user)
        if isinstance(users_dir, bytes):
            users_dir = users_dir.decode('utf-8')
        users_ssh_dir = os.path.join(users_dir, '.ssh')
    else:
        # Fall back to using the default OpenSSH location for ssh stuff
        users_dir = os.environ['HOME']
        if isinstance(users_dir, bytes):
            users_dir = users_dir.decode('utf-8')
        users_ssh_dir = os.path.join(users_dir, '.ssh')

    if not os.path.exists(users_ssh_dir):
        mkdir_p(users_ssh_dir)

    # Download it
    identity_path = os.path.join(users_ssh_dir, identity)
    download_identity(provider, identity, identity_path)

    ssh_config_path = os.path.join(users_ssh_dir, 'config')
    if not os.path.exists(ssh_config_path):
        # Create it (an empty one so ssh doesn't error out)
        with open(ssh_config_path, 'w') as f:
            f.write('\n')

    args = [
        "-x",
        "-F'%s'" % ssh_config_path, # It's OK if it doesn't exist
        # This ensures that the executing users identity won't be used:
        "-oIdentitiesOnly=yes",
        "-oStrictHostKeyChecking=no",
        # This ensures the other end can tell we're a Gate One terminal and
        # possibly use the session ID with plugins (could be interesting).
        "-oSendEnv='GO_TERM GO_LOCATION GO_SESSION'",
        "-p", str(port),
        "-l", user,
    ]

    if debug:
        args.append('-vvv')

    # Now make sure we use it in the connection
    args.insert(3, "-i%s" % identity_path)
    args.insert(3, "-oPreferredAuthentications='publickey'")

    command = None
    if 'PATH' in env:
        command = which("ssh", path=env['PATH'])
    else:
        env['PATH'] = os.environ['PATH']
        command = which("ssh")

    if '[' in host: # IPv6 address
        # Have to remove the brackets which is silly.  See bug:
        #   https://bugzilla.mindrot.org/show_bug.cgi?id=1602
        host = host.strip('[]')

    if additional_args:
        if isinstance(additional_args, (list, tuple)):
            args.extend(additional_args)
        else:
            args.extend(additional_args.split())

    # Command has to go first
    args.insert(0, command)

    # Host should be last
    args.append(host)

    script_path = None
    if 'GO_TERM' in os.environ.keys():
        term = os.environ['GO_TERM']
        location = os.environ['GO_LOCATION']

        if 'GO_SESSION_DIR' in os.environ.keys():
            # Save a file indicating our session is attached to GO_TERM
            ssh_session = 'ssh:%s:%s:%s@%s:%s' % (
                location, term, user, host, port)
            script_path = os.path.join(
                os.environ['GO_SESSION_DIR'],
                os.environ['GO_SESSION'], ssh_session)

    if not script_path:
        # Just use a generic temp file
        temp = tempfile.NamedTemporaryFile(prefix="ssh_connect", delete=False)
        script_path = "%s" % temp.name
        temp.close() # Will be written to below

    # Create our little shell script to wrap the SSH command
    cmd = ""
    for arg in args:
        cmd += arg + ' '

    script = wrapper_script.format(
        cmd=cmd,
        temp=script_path)

    with io.open(script_path, 'w', encoding='utf-8') as f:
        f.write(script)

    # NOTE: We wrap in a shell script so we can execute it and immediately quit.
    # By doing this instead of keeping ssh_connect.py running we can save a lot
    # of memory (depending on how many terminals are open).
    os.chmod(script_path, 0o700) # 0700 for good security practices

    # Execute then immediately quit so we don't use up any more memory than we
    # need.
    # setup default execvpe args
    args = ['-c', script_path, '&&', 'rm', '-f', script_path]

    # If we detect /bin/sh linked to busybox then make sure we insert the 'sh'
    # at the beginning of the args list
    if os.path.islink('/bin/sh'):
        args.insert(0, 'sh')

    os.execvpe('/bin/sh', args, env)
    os._exit(0)

def parse_url(url):
    """
    Parses a URL like, 'ssh://user@host:22' and returns a dict of::

        {
            'scheme': scheme,
            'user': user,
            'host': host,
            'port': port,
            'password': password,
            'provider': provider,
            'identity': identity,
            'debug': debug
        }

    .. note:: 'web+ssh://' URLs are also supported.

    If an ssh URL is given without a username, os.environ['GO_USER'] will be
    used and if that doesn't exist it will fall back to os.environ['USER'].

    SSH identity may be specified as a query string:

        ssh://user@host:22/?provider=name&identity=id_rsa

    .. note::

        *password*, *provider*, and *identity* may be returned as None
    """
    provider = None
    identity = None
    debug = False

    try:
        from urlparse import urlparse, parse_qs, uses_query
        if 'ssh' not in uses_query: # Only necessary in Python 2.X
            uses_query.append('ssh')
    except ImportError: # Python 3
        from urllib.parse import urlparse, parse_qs

    parsed = urlparse(url)
    if parsed.query:
        q_attrs = parse_qs(parsed.query)
        provider = q_attrs.get('provider')[0]
        identity = q_attrs.get('identity')[0]
        debug = q_attrs.get('debug', False)
        if debug: # Passing anything turns on debug
            debug = True

    if parsed.port:
        port = parsed.port
    else:
        port = socket.getservbyname(parsed.scheme, 'tcp')

    return {
        'scheme': parsed.scheme,
        'user': parsed.username,
        'host': parsed.hostname,
        'port': port,
        'password': parsed.password,
        'provider': provider,
        'identity': identity,
        'debug': debug
    }

def bad_chars(chars):
    """
    Returns ``False`` if the given *chars* are OK, ``True`` if there's bad
    characters present (i.e. shell exec funny business).

    .. note::

        This is to prevent things like "ssh://user@host && <malicious commands>"
    """
    bad_chars = re.compile('.*[\$\n\!\;` |<>].*')
    if bad_chars.match(chars):
        return True
    return False

def main():
    """
    Parse command line arguments and execute ssh_connect()
    """
    usage = (
        '\t%prog [options] <ssh://user@host[:port]>'
    )
    parser = OptionParser(usage=usage)
    parser.disable_interspersed_args()

    parser.add_option("-a", "--args",
        dest="additional_args",
        default=None,
        help=("Any additional arguments that should be passed to the ssh "
             "command.  It is recommended to wrap these in quotes."),
        metavar="'<args>'"
    )
    parser.add_option("--default_port",
        dest="default_port",
        default='22',
        help=("The default port that will be used for outbound connections if "
               "no port is provided.  Default: 22"),
        metavar="'<port>'"
    )

    (options, args) = parser.parse_args()

    try:
        # If we're getting a URL as a parameter, try connecting straight away.
        if len(args) == 1:
            # Parse the URL
            parsed = parse_url(args[0])
            user = parsed.get('user')
            host = parsed.get('host')
            port = parsed.get('port')
            provider = parsed.get('provider')
            identity = parsed.get('identity')
            debug=parsed.get('debug', False)

            # Connect
            openssh_connect(user, host, provider, identity,
                port=port,
                additional_args=options.additional_args,
                debug=debug
            )
    except Exception:
        pass

    try:
        # We didn't get a URL as a parameter.  Wait for user input, and
        # validate it.
        url = raw_input("URL: ")

        # Clear screen
        print(chr(27) + "[2J")
        print("Connecting, please wait...")

        # Validate it
        if (not url or
            bad_chars(url) or
            not url.find('://')):
            raise OptionError("Invalid URL")

        # Parse the URL
        parsed = parse_url(url)
        protocol = parsed.get('scheme')
        user = parsed.get('user')
        host = parsed.get('host')
        port = parsed.get('port')
        provider = parsed.get('provider')
        identity = parsed.get('identity')
        debug = parsed.get('debug', False)

        # Validate host
        if not valid_hostname(host):
            # It might be an IPv6 address
            if '[' in host and ']' in host:
                no_brackets = host.strip('[]')
                if not valid_ip(no_brackets):
                    raise OptionError("Invalid IP")
            elif not valid_ip(host):
                raise OptionError("Invalid hostname")

        # Set default port
        if not port:
            port = options.default_port

        # Validate port
        port = int(port)
        if port < 1 or port > 65535:
            raise OptionError("Invalid port")

        # Validate user
        if not user or bad_chars(user):
            raise OptionError("Invalid user")

        # Validate protocol
        if protocol != 'ssh':
            raise OptionError("Invalid protocol")

        # Emit escape handler (so the rest of the plugin knows the connect
        # string)
        connect_string = "{0}@{1}:{2}".format(user, host, port)
        print("\x1b]_;ssh|set;connect_string;{0}\007".format(connect_string))

        # Connect
        openssh_connect(user, host, provider, identity,
            port=port,
            additional_args=options.additional_args,
            debug=debug
        )

    # Ctrl-D
    except (EOFError):
        sys.exit(1)

    # Catch all
    except Exception as e:
        print("Got Exception: %s" % e)
        traceback.print_exc(file=sys.stdout)
        raw_input("[Press any key to close this terminal]")
        sys.exit(1)

if __name__ == "__main__":
    # No zombies
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    executor = futures.ThreadPoolExecutor(max_workers=2)
    try:
        future = executor.submit(main)
        done, not_done = futures.wait([future], timeout=60)
        executor.shutdown(wait=False)
        if not_done:
            print("Took too long.\n")
        else:
            if isinstance(future.exception(), SystemExit):
                print("User exit.\n")
    except (KeyboardInterrupt, EOFError):
        print("User exit.\n")
        os._exit(1)
