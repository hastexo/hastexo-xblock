UP_STATES = (
    'CREATE_COMPLETE',
    'RESUME_COMPLETE',
    'UPDATE_COMPLETE',
    'ROLLBACK_COMPLETE',
    'SNAPSHOT_COMPLETE'
)

SETTINGS_KEY = 'hastexo'

DEFAULT_SETTINGS = {
    "launch_timeout": 300,
    "suspend_timeout": 120,
    "terminal_url": "/terminal",
    "task_timeouts": {
        "sleep": 5,
        "retries": 60
    },
    "js_timeouts": {
        "status": 10000,
        "keepalive": 15000,
        "idle": 600000,
        "check": 5000
    }
}

CREDENTIALS = (
    "os_auth_url",
    "os_auth_token",
    "os_username",
    "os_password",
    "os_user_id",
    "os_user_domain_id",
    "os_user_domain_name",
    "os_project_id",
    "os_project_name",
    "os_project_domain_id",
    "os_project_domain_name",
    "os_region_name"
)


def set_xblock_configuration(settings, defaults={}):
    config = {}
    for key, val in DEFAULT_SETTINGS.iteritems():
        config[key] = settings.get(key, defaults.get(key))

    credentials = {}
    for key in CREDENTIALS:
        credentials[key] = settings.get(key)

    config["credentials"] = credentials

    return config


def get_xblock_configuration(settings, provider):
    # Set defaults
    xblock_configuration = set_xblock_configuration(settings, DEFAULT_SETTINGS)

    # Override defaults with provider settings
    providers = settings.get("providers")
    if providers:
        provider_settings = providers.get(provider)

        if not provider_settings:
            # Fall back to default, if provider is not set.
            provider_settings = providers.get("default")

        if not provider_settings:
            # Fall back to first provider, if no "default" provider exists.
            provider_settings = providers.itervalues().next()

        if provider_settings:
            xblock_configuration = set_xblock_configuration(
                provider_settings, xblock_configuration)

    return xblock_configuration
