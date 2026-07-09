from .paths import AppPaths

PATHS = AppPaths.defaults()

DATA_DIR = PATHS.data_dir
AGENT_DIR = PATHS.agent_dir
AGENT_PROFILES_DIR = PATHS.legacy_agent_profiles_dir
EMPLOYEES_DIR = AGENT_PROFILES_DIR  # legacy compatibility path name
SQLITE_PATH = PATHS.sqlite_path
SMITH_TEMPLATE_ID = "personal-assistant"
SMITH_PROFILE_DIR = PATHS.smith_profile_dir
TEMPLATES_DIR = PATHS.project_root / "agents" / "templates"
BUILTIN_SKILLS_DIR = PATHS.builtin_skills_dir
BUILTIN_TOOLS_DIR = PATHS.builtin_tools_dir
SAFETY_RULES_PATH = PATHS.safety_rules_path
BUILTIN_PLUGINS_DIR = PATHS.builtin_plugins_dir
USER_PLUGINS_DIR = PATHS.user_plugins_dir


def ensure_dirs() -> None:
    PATHS.ensure_base_dirs()
