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
    "ssh_dir": "/edx/var/edxapp/terminal_users/ANONYMOUS/.ssh",
    "ssh_upload": False,
    "ssh_bucket": "identities",
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

def get_xblock_configuration(settings, provider):
    # Set defaults
    launch_timeout = settings.get("launch_timeout", DEFAULT_SETTINGS["launch_timeout"])
    suspend_timeout = settings.get("suspend_timeout", DEFAULT_SETTINGS["suspend_timeout"])
    terminal_url = settings.get("terminal_url", DEFAULT_SETTINGS["terminal_url"])
    ssh_dir = settings.get("ssh_dir", DEFAULT_SETTINGS["ssh_dir"])
    ssh_upload = settings.get("ssh_upload", DEFAULT_SETTINGS["ssh_upload"])
    ssh_bucket = settings.get("ssh_bucket", DEFAULT_SETTINGS["ssh_bucket"])
    task_timeouts = settings.get("task_timeouts", DEFAULT_SETTINGS["task_timeouts"])
    js_timeouts = settings.get("js_timeouts", DEFAULT_SETTINGS["js_timeouts"])

    # Get credentials
    providers = settings.get("providers")
    if providers:
        credentials = providers.get(provider)
        if not credentials:
            credentials = providers.get("default")
        if not credentials:
            credentials = providers.itervalues().next()
    else:
        # For backward compatibility.
        credentials = {
            "os_auth_url": settings.get("os_auth_url"),
            "os_auth_token": settings.get("os_auth_token"),
            "os_username": settings.get("os_username"),
            "os_password": settings.get("os_password"),
            "os_user_id": settings.get("os_user_id"),
            "os_user_domain_id": settings.get("os_user_domain_id"),
            "os_user_domain_name": settings.get("os_user_domain_name"),
            "os_project_id": settings.get("os_project_id"),
            "os_project_name": settings.get("os_project_name"),
            "os_project_domain_id": settings.get("os_project_domain_id"),
            "os_project_domain_name": settings.get("os_project_domain_name"),
            "os_region_name": settings.get("os_region_name")
        }

    return {
        "launch_timeout": launch_timeout,
        "suspend_timeout": suspend_timeout,
        "terminal_url": terminal_url,
        "ssh_dir": ssh_dir,
        "ssh_upload": ssh_upload,
        "ssh_bucket": ssh_bucket,
        "task_timeouts": task_timeouts,
        "js_timeouts": js_timeouts,
        "credentials": credentials
    }
